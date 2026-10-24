// SPDX-License-Identifier: GPL-2.0-or-later
// Opt-in preload for the capture experiment only. No Vulkan/rendering interception.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../gpu/third_party/renderdoc/renderdoc_app.h"

static void *capture_worker(void *unused) {
    (void)unused;
    // Only use RenderDoc already injected by renderdoccmd; never load it into production.
    void *module = dlopen("librenderdoc.so", RTLD_NOW | RTLD_NOLOAD);
    pRENDERDOC_GetAPI get_api = module ? (pRENDERDOC_GetAPI)dlsym(module, "RENDERDOC_GetAPI") : NULL;
    RENDERDOC_API_1_6_0 *api = NULL;
    if (!get_api || get_api(eRENDERDOC_API_Version_1_6_0, (void **)&api) != 1) {
        fprintf(stderr, "SOTC capture: RenderDoc API unavailable; no capture armed\n");
        return NULL;
    }
    const char *trigger = getenv("SOTC_PIXEL_TRIGGER");
    api->SetCaptureFilePathTemplate(getenv("SOTC_PIXEL_OUTPUT"));
    fprintf(stderr, "SOTC capture: RenderDoc attached; waiting for %s\n", trigger);
    unsigned reported = api->GetNumCaptures();
    int requested = 0;
    for (;;) {
        if (!requested && unlink(trigger) == 0) {
            // Let RenderDoc delimit complete frames at presents, not arbitrary CP submits.
            api->TriggerMultiFrameCapture(3);
            requested = 1;
            fprintf(stderr, "SOTC capture: requested three consecutive presented frames\n");
        }
        unsigned count = api->GetNumCaptures();
        while (reported < count) {
            uint32_t length = 0;
            api->GetCapture(reported, NULL, &length, NULL);
            char *path = calloc((size_t)length + 1, 1);
            if (path && api->GetCapture(reported, path, &length, NULL))
                fprintf(stderr, "SOTC capture: saved %s\n", path);
            free(path);
            ++reported;
        }
        usleep(200000);
    }
    return NULL;
}

__attribute__((constructor)) static void start_capture_helper(void) {
    if (!getenv("SOTC_PIXEL_TRIGGER") || !getenv("SOTC_PIXEL_OUTPUT")) return;
    char executable[4096];
    ssize_t n = readlink("/proc/self/exe", executable, sizeof(executable) - 1);
    if (n < 0) return;
    executable[n] = 0;
    const char *base = strrchr(executable, '/');
    if (strcmp(base ? base + 1 : executable, "bb-probe") != 0) return;
    pthread_t thread;
    if (pthread_create(&thread, NULL, capture_worker, NULL) == 0) pthread_detach(thread);
    else fprintf(stderr, "SOTC capture: could not create capture helper\n");
}
