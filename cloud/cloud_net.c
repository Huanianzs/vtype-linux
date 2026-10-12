/* Linux：普通拼音云查询（4329/2）与官方引擎自身的词库同步（4814）交给宿主代理。
 * 云查询走 SEQPACKET；同步请求和响应可达数百 KB，走独立的分帧 stream 通道。
 * 放行哪些同步子命令由宿主白名单决定，这里只负责搬运。 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <pthread.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#include <sys/uio.h>
#define MAGIC 0x57434c31u
#define LIMIT 65536
#define SLOTS 128
typedef void (*Callback)(void *,int,int,const char *,unsigned,const char *,unsigned);
typedef struct {unsigned id;Callback cb;void *user;char query[256];} Task;
static Task tasks[SLOTS];
static pthread_mutex_t mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ready=PTHREAD_COND_INITIALIZER;
static int transport=-1,started;
static unsigned sequence;
static char local_input[256];

static uint64_t varint(const unsigned char *b,unsigned size,unsigned *at) {
    uint64_t n=0;unsigned shift=0;
    while(*at<size && shift<64){unsigned c=b[(*at)++];n|=(uint64_t)(c&127)<<shift;if(c<128)return n;shift+=7;}
    *at=size;return 0;
}
static int query(const unsigned char *b,unsigned size,char *out) {
    unsigned at=0,used=0;
    while(at<size){uint64_t tag=varint(b,size,&at);unsigned wire=tag&7;
        if(wire==0){varint(b,size,&at);continue;}
        if(wire!=2)return 0;
        unsigned n=varint(b,size,&at);if(n>size-at)return 0;
        if((tag>>3)==4){unsigned p=0;const unsigned char *in=b+at;
            while(p<n){uint64_t t=varint(in,n,&p);unsigned w=t&7;
                if(w==0){varint(in,n,&p);continue;}if(w!=2)return 0;
                unsigned len=varint(in,n,&p);if(len>n-p)return 0;
                if((t>>3)==3){if(used+len>=256)return 0;memcpy(out+used,in+p,len);used+=len;}
                p+=len;
            }
        }
        at+=n;
    }
    out[used]=0;return used>0;
}
void wetype_cloud_ready(const char *input) {
    pthread_mutex_lock(&mu);snprintf(local_input,sizeof local_input,"%s",input?input:"");
    pthread_cond_broadcast(&ready);pthread_mutex_unlock(&mu);
}
void wetype_cloud_reset(void) {wetype_cloud_ready("");}
static void finish(unsigned id,int code,const char *body,unsigned size) {
    Task task={0};pthread_mutex_lock(&mu);
    if(tasks[id%SLOTS].id==id){task=tasks[id%SLOTS];memset(&tasks[id%SLOTS],0,sizeof task);}
    if(task.cb && !code){
        struct timespec end;clock_gettime(CLOCK_REALTIME,&end);end.tv_nsec+=400000000;
        if(end.tv_nsec>=1000000000){end.tv_nsec-=1000000000;end.tv_sec++;}
        while(strcmp(local_input,task.query)){
            if(pthread_cond_timedwait(&ready,&mu,&end)==ETIMEDOUT){code=-2;break;}
        }
    }
    pthread_mutex_unlock(&mu);
    if(task.cb)task.cb(task.user,id,code,code?"":body,code?0:size,"",0);
}
static void *receive(void *unused) {
    unsigned char packet[LIMIT+16];ssize_t n;
    while((n=recv(transport,packet,sizeof packet,0))>0){
        uint32_t header[4];if(n<16)continue;memcpy(header,packet,16);
        if(header[0]!=MAGIC || header[3]!=(unsigned)n-16)continue;
        finish(header[1],(int32_t)header[2],(char *)packet+16,header[3]);
    }
    for(unsigned i=0;i<SLOTS;i++){pthread_mutex_lock(&mu);unsigned id=tasks[i].id;pthread_mutex_unlock(&mu);if(id)finish(id,-2,"",0);}
    return NULL;
}
#define SYNC_MAGIC 0x57534e31u
#define SYNC_LIMIT (4*1024*1024)
typedef struct {unsigned id;Callback cb;void *user;} SyncTask;
static SyncTask sync_tasks[SLOTS];
static pthread_mutex_t sync_mu=PTHREAD_MUTEX_INITIALIZER;
static int sync_fd=-1;
static unsigned sync_sequence;
static int sync_io(int write_mode,void *buf,size_t n) {
    char *p=buf;
    while(n){ssize_t r=write_mode?send(sync_fd,p,n,MSG_NOSIGNAL):read(sync_fd,p,n);
        if(r<0&&errno==EINTR)continue;if(r<=0)return 0;p+=r;n-=(size_t)r;}
    return 1;
}
static void sync_finish(unsigned id,int code,const char *body,unsigned size) {
    SyncTask task={0};pthread_mutex_lock(&sync_mu);
    if(sync_tasks[id%SLOTS].id==id){task=sync_tasks[id%SLOTS];memset(&sync_tasks[id%SLOTS],0,sizeof task);}
    pthread_mutex_unlock(&sync_mu);
    if(task.cb)task.cb(task.user,id,code,code?"":body,code?0:size,"",0);
}
static void *sync_receive(void *unused) {
    char *packet=malloc(SYNC_LIMIT);uint32_t header[4];
    while(packet && sync_io(0,header,sizeof header)){
        if(header[0]!=SYNC_MAGIC || header[3]>SYNC_LIMIT || !sync_io(0,packet,header[3]))break;
        sync_finish(header[1],(int32_t)header[2],packet,header[3]);
    }
    for(unsigned i=0;i<SLOTS;i++){pthread_mutex_lock(&sync_mu);unsigned id=sync_tasks[i].id;pthread_mutex_unlock(&sync_mu);if(id)sync_finish(id,-2,"",0);}
    free(packet);return NULL;
}
static int sync_start(unsigned command,unsigned subcommand,const char *body,unsigned size,void *user,Callback cb) {
    if(sync_fd<0 || !cb || size>SYNC_LIMIT || (size && !body))return -1;
    pthread_mutex_lock(&sync_mu);unsigned id=++sync_sequence;if(!id)id=++sync_sequence;
    if(sync_tasks[id%SLOTS].id){pthread_mutex_unlock(&sync_mu);return -1;}
    sync_tasks[id%SLOTS]=(SyncTask){id,cb,user};
    uint32_t header[]={SYNC_MAGIC,id,command,subcommand,size};
    int ok=sync_io(1,header,sizeof header)&&(!size||sync_io(1,(void *)body,size));
    if(!ok)memset(&sync_tasks[id%SLOTS],0,sizeof(SyncTask));
    pthread_mutex_unlock(&sync_mu);
    return ok?(int)id:-1;
}
int net_start_task_with_option(void *context,unsigned command,unsigned subcommand,
    const char *body,unsigned size,const void *option,void *user,Callback cb) {
    if(command==4814)return sync_start(command,subcommand,body,size,user,cb);
    if(command!=4329 || subcommand!=2 || !body || !cb || size>8192 || transport<0)return -1;
    Task task={.cb=cb,.user=user};if(!query((const unsigned char *)body,size,task.query))return -1;
    pthread_mutex_lock(&mu);unsigned id=++sequence;if(!id)id=++sequence;
    if(tasks[id%SLOTS].id){pthread_mutex_unlock(&mu);return -1;}
    task.id=id;tasks[id%SLOTS]=task;
    uint32_t header[]={MAGIC,id,command,subcommand,size};
    struct iovec vec[]={{header,sizeof header},{(void *)body,size}};
    struct msghdr msg={.msg_iov=vec,.msg_iovlen=2};
    ssize_t n=sendmsg(transport,&msg,MSG_DONTWAIT|MSG_NOSIGNAL);
    if(n!=(ssize_t)(sizeof header+size))memset(&tasks[id%SLOTS],0,sizeof task);
    pthread_mutex_unlock(&mu);
    return n==(ssize_t)(sizeof header+size)?(int)id:-1;
}
void net_initialize(void *context,const void *config,void *user,void (*done)(void *,int,int,const char *)) {
    pthread_mutex_lock(&mu);
    if(!started){started=1;const char *fd=getenv("WETYPE_CLOUD_FD");
        if(fd){transport=atoi(fd);pthread_t thread;if(pthread_create(&thread,NULL,receive,NULL))transport=-1;else pthread_detach(thread);}
        const char *sfd=getenv("WETYPE_SYNC_FD");
        if(sfd){sync_fd=atoi(sfd);pthread_t thread;if(pthread_create(&thread,NULL,sync_receive,NULL))sync_fd=-1;else pthread_detach(thread);}}
    pthread_mutex_unlock(&mu);
    if(done)done(user,transport>=0?0:-2,0,NULL);
}
void net_initialize_get_uin(void *context,const void *config,void *callback) {}
