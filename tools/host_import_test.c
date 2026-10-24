/* sotc: can the GPU use the game's memory in place? (prototype for the "PC memory model")
 *
 * Maps a pagefile-backed section twice, as src/runtime_memory.c maps the game's direct memory
 * (a backing view and a guest view that replaces a placeholder), imports the backing view into
 * Vulkan with VK_EXT_external_memory_host and checks, for several sizes:
 *   1. the import succeeds and which memory types accept it;
 *   2. a GPU write (vkCmdFillBuffer) is seen by the CPU through the guest view;
 *   3. a CPU write through the guest view is read by the GPU (vkCmdCopyBuffer into a
 *      device-local buffer and back);
 *   4. GPU read bandwidth of imported memory against device-local memory.
 * Build: clang -O2 tools/host_import_test.c -o out/host_import_test.exe -lvulkan-1 -lonecore (CLANG64). */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

#define CHECK(call) do { VkResult r_ = (call); if (r_ != VK_SUCCESS) { printf("  %s failed: %d\n", #call, r_); return 1; } } while (0)

static VkInstance instance;
static VkPhysicalDevice gpu;
static VkDevice device;
static VkQueue queue;
static uint32_t queue_family;
static VkCommandPool pool;
static PFN_vkGetMemoryHostPointerPropertiesEXT get_host_pointer_properties;
static VkPhysicalDeviceMemoryProperties memory;

static int setup(void) {
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_3};
    VkInstanceCreateInfo ici = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    CHECK(vkCreateInstance(&ici, NULL, &instance));
    uint32_t count = 8;
    VkPhysicalDevice gpus[8];
    CHECK(vkEnumeratePhysicalDevices(instance, &count, gpus));
    for (uint32_t i = 0; i < count && !gpu; ++i) {
        VkPhysicalDeviceProperties p;
        vkGetPhysicalDeviceProperties(gpus[i], &p);
        if (p.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) { gpu = gpus[i]; printf("GPU: %s\n", p.deviceName); }
    }
    if (!gpu) gpu = gpus[0];
    vkGetPhysicalDeviceMemoryProperties(gpu, &memory);
    uint32_t families = 16;
    VkQueueFamilyProperties qf[16];
    vkGetPhysicalDeviceQueueFamilyProperties(gpu, &families, qf);
    for (queue_family = 0; queue_family < families && !(qf[queue_family].queueFlags & VK_QUEUE_GRAPHICS_BIT); ++queue_family) {}
    float priority = 1;
    VkDeviceQueueCreateInfo qci = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex = queue_family,
                                   .queueCount = 1, .pQueuePriorities = &priority};
    const char *extensions[] = {VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME};
    VkDeviceCreateInfo dci = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount = 1,
                              .pQueueCreateInfos = &qci, .enabledExtensionCount = 1, .ppEnabledExtensionNames = extensions};
    CHECK(vkCreateDevice(gpu, &dci, NULL, &device));
    vkGetDeviceQueue(device, queue_family, 0, &queue);
    VkCommandPoolCreateInfo pci = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, .queueFamilyIndex = queue_family,
                                   .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT};
    CHECK(vkCreateCommandPool(device, &pci, NULL, &pool));
    get_host_pointer_properties = (PFN_vkGetMemoryHostPointerPropertiesEXT)vkGetDeviceProcAddr(device, "vkGetMemoryHostPointerPropertiesEXT");
    return get_host_pointer_properties ? 0 : 1;
}

static int buffer_on(VkDeviceMemory mem, VkDeviceSize size, VkBuffer *out, int external) {
    VkExternalMemoryBufferCreateInfo ext = {.sType = VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_BUFFER_CREATE_INFO,
                                            .handleTypes = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT};
    VkBufferCreateInfo bci = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .pNext = external ? &ext : NULL, .size = size,
                              .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT |
                                       VK_BUFFER_USAGE_STORAGE_BUFFER_BIT};
    CHECK(vkCreateBuffer(device, &bci, NULL, out));
    CHECK(vkBindBufferMemory(device, *out, mem, 0));
    return 0;
}

static double run(void (*record)(VkCommandBuffer, void *), void *arg) {
    VkCommandBuffer cb;
    VkCommandBufferAllocateInfo ai = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, .commandPool = pool,
                                      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    vkAllocateCommandBuffers(device, &ai, &cb);
    VkCommandBufferBeginInfo bi = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
                                   .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    vkBeginCommandBuffer(cb, &bi);
    record(cb, arg);
    vkEndCommandBuffer(cb);
    VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cb};
    LARGE_INTEGER f, a, b;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&a);
    vkQueueSubmit(queue, 1, &si, VK_NULL_HANDLE);
    vkQueueWaitIdle(queue);
    QueryPerformanceCounter(&b);
    vkFreeCommandBuffers(device, pool, 1, &cb);
    return (double)(b.QuadPart - a.QuadPart) / f.QuadPart;
}

typedef struct { VkBuffer src, dst; VkDeviceSize offset, size; uint32_t value; } Op;
static void record_fill(VkCommandBuffer cb, void *p) { Op *o = p; vkCmdFillBuffer(cb, o->dst, o->offset, o->size, o->value); }
static void record_copy(VkCommandBuffer cb, void *p) {
    Op *o = p;
    VkBufferCopy region = {.srcOffset = o->offset, .dstOffset = 0, .size = o->size};
    vkCmdCopyBuffer(cb, o->src, o->dst, 1, &region);
}

static int test(uint64_t size) {
    printf("\n== %llu MiB\n", (unsigned long long)(size >> 20));
    HANDLE section = CreateFileMapping2(INVALID_HANDLE_VALUE, NULL, FILE_MAP_ALL_ACCESS, PAGE_EXECUTE_READWRITE, SEC_COMMIT,
                                        size, NULL, NULL, 0);
    if (!section) { printf("  section failed %lu\n", GetLastError()); return 1; }
    unsigned char *backing = MapViewOfFile3(section, GetCurrentProcess(), NULL, 0, size, 0, PAGE_READWRITE, NULL, 0);
    void *placeholder = VirtualAlloc2(NULL, NULL, size, MEM_RESERVE | MEM_RESERVE_PLACEHOLDER, PAGE_NOACCESS, NULL, 0);
    unsigned char *guest = placeholder ? MapViewOfFile3(section, GetCurrentProcess(), placeholder, 0, size, MEM_REPLACE_PLACEHOLDER,
                                                        PAGE_READWRITE, NULL, 0) : NULL;
    if (!backing || !guest) { printf("  views failed %lu\n", GetLastError()); return 1; }

    VkMemoryHostPointerPropertiesEXT props = {.sType = VK_STRUCTURE_TYPE_MEMORY_HOST_POINTER_PROPERTIES_EXT};
    VkResult r = get_host_pointer_properties(device, VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT, backing, &props);
    printf("  host pointer properties: %d, memory types 0x%x\n", r, props.memoryTypeBits);
    if (r != VK_SUCCESS || !props.memoryTypeBits) return 1;
    uint32_t type = 0;
    while (!(props.memoryTypeBits & (1u << type))) ++type;
    VkMemoryPropertyFlags flags = memory.memoryTypes[type].propertyFlags;
    printf("  type %u: %s%s%s\n", type, flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT ? "coherent " : "",
           flags & VK_MEMORY_PROPERTY_HOST_CACHED_BIT ? "cached " : "", flags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT ? "device-local" : "");
    VkImportMemoryHostPointerInfoEXT import = {.sType = VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT,
                                               .handleType = VK_EXTERNAL_MEMORY_HANDLE_TYPE_HOST_ALLOCATION_BIT_EXT,
                                               .pHostPointer = backing};
    VkMemoryAllocateInfo mai = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .pNext = &import, .allocationSize = size,
                                .memoryTypeIndex = type};
    VkDeviceMemory imported;
    LARGE_INTEGER f, a, b;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&a);
    r = vkAllocateMemory(device, &mai, NULL, &imported);
    QueryPerformanceCounter(&b);
    printf("  import: %d (%.1f ms)\n", r, 1000.0 * (b.QuadPart - a.QuadPart) / f.QuadPart);
    if (r != VK_SUCCESS) return 1;
    VkBuffer host_buffer;
    if (buffer_on(imported, size, &host_buffer, 1)) return 1;

    /* 2: GPU writes, CPU reads through the guest view. */
    Op fill = {.dst = host_buffer, .offset = size / 2, .size = 1 << 20, .value = 0xC0105505u};
    run(record_fill, &fill);
    int ok = 1;
    for (uint64_t i = size / 2; i < size / 2 + (1 << 20); i += 4) ok &= *(uint32_t *)(guest + i) == 0xC0105505u;
    printf("  GPU write seen by the CPU (guest view): %s\n", ok ? "yes" : "NO");

    /* 3: CPU writes through the guest view, GPU reads. */
    const VkDeviceSize chunk = 256u << 20 < size ? 256u << 20 : size;
    for (uint64_t i = 0; i < chunk; i += 4) *(uint32_t *)(guest + i) = (uint32_t)(i * 2654435761u);
    uint32_t local_type = 0;
    for (; local_type < memory.memoryTypeCount; ++local_type)
        if (memory.memoryTypes[local_type].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) break;
    VkMemoryAllocateInfo lai = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = chunk, .memoryTypeIndex = local_type};
    VkDeviceMemory local;
    CHECK(vkAllocateMemory(device, &lai, NULL, &local));
    VkBuffer local_buffer;
    if (buffer_on(local, chunk, &local_buffer, 0)) return 1;
    Op copy = {.src = host_buffer, .dst = local_buffer, .offset = 0, .size = chunk};
    double t_in = run(record_copy, &copy);
    memset(guest, 0, chunk);
    Op back = {.src = local_buffer, .dst = host_buffer, .offset = 0, .size = chunk};
    run(record_copy, &back);
    ok = 1;
    for (uint64_t i = 0; i < chunk; i += 4) ok &= *(uint32_t *)(guest + i) == (uint32_t)(i * 2654435761u);
    printf("  CPU write read by the GPU and copied back: %s\n", ok ? "yes" : "NO");
    printf("  GPU reads imported memory at %.1f GB/s\n", chunk / t_in / 1e9);
    VkDeviceMemory local2;
    CHECK(vkAllocateMemory(device, &lai, NULL, &local2));
    VkBuffer local_buffer2;
    if (buffer_on(local2, chunk, &local_buffer2, 0)) return 1;
    Op vram = {.src = local_buffer, .dst = local_buffer2, .offset = 0, .size = chunk};
    run(record_copy, &vram);
    printf("  (device-local copy at %.1f GB/s)\n", chunk / run(record_copy, &vram) / 1e9);

    vkDestroyBuffer(device, local_buffer2, NULL);
    vkFreeMemory(device, local2, NULL);
    vkDestroyBuffer(device, local_buffer, NULL);
    vkFreeMemory(device, local, NULL);
    vkDestroyBuffer(device, host_buffer, NULL);
    vkFreeMemory(device, imported, NULL);
    UnmapViewOfFile2(GetCurrentProcess(), guest, 0);
    UnmapViewOfFile(backing);
    CloseHandle(section);
    return 0;
}

int main(int argc, char **argv) {
    if (setup()) { puts("setup failed"); return 1; }
    int failed = 0;
    for (int i = 1; i < argc; ++i) failed |= test(strtoull(argv[i], NULL, 0) << 20);
    if (argc < 2) failed |= test(256ull << 20) | test(2048ull << 20) | test(5120ull << 20);
    return failed;
}
