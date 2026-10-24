/* Real SaveData mounts/backups + guest file I/O across separate processes.
 * Only temporary synthetic profiles are used. */
#include "../src/runtime_savedata.c"
#include <assert.h>
#include <sys/wait.h>
static int32_t guest_errno;
int32_t *runtime_errno(void) { return &guest_errno; }
int32_t runtime_guest_errno(int e) { return e; }
uintptr_t runtime_lookup(const RuntimeExport *table,size_t n,const char *name) {
    for (size_t i=0;i<n;++i) if (!strcmp(table[i].name,name)) return (uintptr_t)table[i].function;
    return 0;
}
static const DirName names[]={ {"SAVEDATA0ShadowProfile0"}, {"SAVEDATA0ShadowProgress0"} };
static void configure(const char *user) {
    runtime_file_configure("/unused-synthetic-app0",user);
    runtime_savedata_configure("CUSA08809");
    assert(!save_initialize(NULL));
}
static MountResult mount_save(unsigned name,uint32_t mode) {
    Mount2 m={.user=1,.dir=&names[name],.blocks=96,.mode=mode};
    MountResult r;
    assert(!save_mount2(&m,&r));
    return r;
}
static void verify(unsigned name,const char *expected) {
    MountResult r=mount_save(name,MODE_RDONLY);
    assert(!strcmp(r.point.data,"/savedata0") && !runtime_savedata_mounted());
    int fd=(int)runtime_file_open("/savedata0/USR-DATA",0,0); assert(fd>=3);
    char bytes[128]={0};
    assert(runtime_file_read(fd,bytes,sizeof(bytes))==(int64_t)strlen(expected));
    assert(!strcmp(bytes,expected) && !runtime_file_close(fd));
    assert(!save_umount_backup(&r.point));
    assert(runtime_file_open("/savedata0/USR-DATA",0,0)<0);
}
static void write_save(unsigned name,const char *bytes,int backup) {
    MountResult r=mount_save(name,MODE_CREATE2|2);
    assert(runtime_savedata_mounted()==1);
    int fd=(int)runtime_file_open("/savedata0/USR-DATA",0x602,0644); assert(fd>=3);
    assert(runtime_file_write(fd,bytes,strlen(bytes))==(int64_t)strlen(bytes));
    assert(!runtime_file_close(fd));
    assert(!(backup ? save_umount_backup(&r.point) : save_umount(&r.point)));
    assert(!runtime_savedata_mounted());
}
static void check_file(const char *user,unsigned name,const char *suffix,const char *expected) {
    char path[1200],bytes[128]={0};
    snprintf(path,sizeof(path),"%s/savedata/1/CUSA08809/%s%s",user,names[name].data,suffix);
    FILE *f=fopen(path,"rb"); assert(f);
    assert(fread(bytes,1,sizeof(bytes),f)==strlen(expected));
    assert(!strcmp(bytes,expected) && !fclose(f));
}
int main(int argc,char **argv) {
    if (argc==3) {
        assert(!chdir("/"));
        configure(argv[1]);
        verify(0,"profile-written"); verify(1,argv[2]);
        assert(!save_terminate());
        return 0;
    }
    assert(argc==1);
    char temporary[]="/tmp/sotc-savedata-XXXXXX";
    assert(mkdtemp(temporary));
    configure(temporary);
    write_save(0,"profile-written",1); write_save(1,"progress-old",1);
    verify(0,"profile-written"); verify(1,"progress-old");
    /* The newer main copy must win over an older .sce_backup. */
    write_save(1,"progress-newer",0);
    check_file(temporary,1,".sce_backup/data/USR-DATA","progress-old");
    pid_t child=fork(); assert(child>=0);
    if (!child) { execl("/proc/self/exe",argv[0],temporary,"progress-newer",NULL); _exit(127); }
    int status; assert(waitpid(child,&status,0)==child && WIFEXITED(status) && !WEXITSTATUS(status));
    check_file(temporary,1,"/USR-DATA","progress-newer");
    check_file(temporary,1,".sce_backup/data/USR-DATA","progress-old");
    assert(!save_terminate());
    remove_tree(temporary);
    puts("PASS: profile/progress persist across processes; readonly load preserves newer saves and backups");
}
