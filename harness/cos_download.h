/* 官方 JNI COS 下载宿主桥。上传不传文件、异步报告失败；下载完成后通知官方引擎。 */
#include <sys/socket.h>
#define COS_MAGIC 0x57434f31u
static int cos_fd=-1,cos_next=1;
static pthread_mutex_t cos_mu=PTHREAD_MUTEX_INITIALIZER;
static void (*cos_complete)(void *,void *,int,int);
static void *cos_env;
static int cos_io(void *buf,size_t len,int writing) {
    unsigned char *p=buf;
    while(len){ssize_t n=writing?send(cos_fd,p,len,MSG_NOSIGNAL):recv(cos_fd,p,len,0);
        if(n<0 && errno==EINTR)continue;if(n<=0)return -1;p+=n;len-=n;}
    return 0;
}
static void *cos_reader(void *unused) {
    uint32_t r[3];
    while(!cos_io(r,sizeof r,0)) {
        if(r[0]!=COS_MAGIC)break;
        /* 与 Android 异步任务一致，避免在 onClientCosAPI 尚未返回时完成。 */
        usleep(100000);
        cos_complete(cos_env,NULL,(int)r[1],(int)r[2]);
        fprintf(stderr,"[cos] download complete code=%d\n",(int)r[2]);
    }
    return NULL;
}
static void *cos_reject_upload(void *job) {
    usleep(100000);cos_complete(cos_env,NULL,(int)(intptr_t)job,-1);
    fprintf(stderr,"[cos] upload blocked, failure delivered\n");return NULL;
}
static long cos_request(JIDToken *id,JObj *param,int download) {
    if(!id || strcmp(id->name,"onClientCosAPI") || cos_fd<0)return -1;
    if(!download){
        pthread_mutex_lock(&cos_mu);int job=cos_next>0 && cos_next<INT32_MAX?cos_next++:-1;pthread_mutex_unlock(&cos_mu);
        if(job<0)return -1;
        pthread_t thread;if(pthread_create(&thread,NULL,cos_reject_upload,(void *)(intptr_t)job))return -1;
        pthread_detach(thread);return job;
    }
    const char *names[]={"bucket_name","file_path","key","url"},*values[4];
    uint32_t frame[6]={COS_MAGIC,0,0,0,0,0};
    for(int i=0;i<4;i++){
        JField *f=param?obj_get(param,names[i]):NULL;
        if(!f || f->type!='s' || !f->val)return -1;
        values[i]=f->val;size_t n=strlen(values[i]);if(!n || n>16384)return -1;frame[i+2]=(uint32_t)n;
    }
    pthread_mutex_lock(&cos_mu);
    if(cos_next<=0 || cos_next==INT32_MAX){pthread_mutex_unlock(&cos_mu);return -1;}
    int job=cos_next++;frame[1]=job;int err=cos_io(frame,sizeof frame,1);
    for(int i=0;i<4 && !err;i++)err=cos_io((void *)values[i],frame[i+2],1);
    pthread_mutex_unlock(&cos_mu);
    if(err)return -1;
    fprintf(stderr,"[cos] download accepted\n");return job;
}
static void cos_start(void *h,void *env) {
    const char *s=getenv("WETYPE_COS_FD");if(!s)return;
    char *end;long fd=strtol(s,&end,10);if(*end || fd<3 || fd>INT32_MAX)return;
    void (*enable)(void *,void *,unsigned char)=dlsym(h,"_Z28enable_native_client_cos_apiP7_JNIEnvP7_jclassh");
    cos_complete=dlsym(h,"_Z23client_cos_job_completeP7_JNIEnvP7_jclassii");
    if(!enable || !cos_complete)return;
    cos_fd=(int)fd;cos_env=env;pthread_t thread;
    if(pthread_create(&thread,NULL,cos_reader,NULL)){cos_fd=-1;return;}
    pthread_detach(thread);enable(env,NULL,1);
}
