#!/usr/bin/python  
# -*- coding: UTF-8 -*-
# Todos:
# 1.读取配置文件
# 2.获取transmission 下载列表
# 3.筛查未处理的种子的每一个文件，命中过滤条件的，设为不下载
# 4.如设定了单个种子的上传速度上线，设置上传上限

import os
import json
import time
import subprocess

#--- 函数 -----------------------------------------


#关键字过滤，包含匹配
def debugLog(msg):
    debugLog = "debug.log"
    if os.path.exists(debugLog):
        f = open(debugLog, 'a')
    else:
        f = open(debugLog, 'w')            
    f.write(time.strftime("%Y/%m/%d %H:%M:%S")+":"+str(msg)+"\n")
    f.close()
    return

def errLog(msg):
    log = "error.log"
    if os.path.exists(log):
        f = open(log, 'a')
    else:
        f = open(log, 'w')    
    f.write(time.strftime("%Y/%m/%d %H:%M:%S")+":"+str(msg)+"\n")
    f.close()
    return    

def hitKey(filename, keys):
    filename = filename.decode('utf-8');
    for key in keys:
        if key in filename:
            return True;
    
    return False;

#黑名单校对，精确匹配
def hitBlackList(filename, list):
    if not list: #空的黑名单
        return False
    
    for target in list:
        target = target.strip()
        if target in filename:
            return True    
    
    return False
    
def seedHash(tId):
    #transmission-remote -t 104 -i | grep Hash
    #Hash: 7d60776ccab4f85f82f3b26fca3b516cc8a78eba    
    p = subprocess.Popen('transmission-remote -t '+str(tId)+' -i | grep Hash', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
 
    #print(p.stdout)
    #print(p.stderr)
    output = str(p.stdout.readline()) #只要读一行就好了。只有一行
    if "Hash" in output:
        parts = output.split()
        return parts[1] #Hash

    return "" #目标不存在，或者未解析出文件，暂不处理
#查找hash是否存在于log中
def recordInLog(hash, logs): 
    if len(hash)<1: #无效的hash,返回 True 目的使到该行不被处理
        #if madeDebugLog: debugLog("recordInLog.hash too sort") #debug
        return True;
    
    if not logs:
        #if madeDebugLog: debugLog("recordInLog.no logs") #debug
        return False #log不存在，有效的
    
    for line in logs:
        if hash in line:
            #if madeDebugLog: debugLog("recordInLog.hit logs") #debug
            return True
    
    #if madeDebugLog: debugLog("recordInLog.no hit logs") #debug
    return False

#添加hash到log中
def logHash(hash, logfile): 
    if os.path.exists(logfile):
        f = open(logfile, 'a')
    else:
        f = open(logfile, 'w')    
    f.write(str(time.time())+","+hash+'\n')
    f.close()
    return




#--- 业务流程 ----------------------------------------------

#init
config_file = open('setting.json')
cfg = config_file.read();
#print(cfg) #debug
conf = json.loads(cfg)
#print(conf)
config_file.close();
keys = conf["filter"]
checkBlacklist = conf['blacklist_enabled'] != 0 #False #由conf决定

blacklist = None
if checkBlacklist:
    try:
        bl = open(conf["blacklist"])
        blacklist = bl.readlines()
    except Exception as err:
        errLog(err)
        exit(err)

#hash日志文件
logfile = "hash.log"    
hashlogs = None 
#以防文件不存在
try:
    f = open(logfile)
    hashlogs = f.readlines()
    f.close()    
except Exception as err:
    errLog(err)

#debug参数
madeDebugLog = False
if conf["debug"]==1:
    madeDebugLog =True

#读取列表
p = subprocess.Popen("transmission-remote -l | grep -v 'Ratio\\|Sum:'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) #注意 '\\|' 转义2重
for line in p.stdout.readlines():    
    #line = line.decode()
    #if madeDebugLog: 
    #   debugLog("line:"+line.decode()) #debug
    
    parts = line.split() #id, %, 其他的不用关心
    seedId = parts[0]
    
    if not line: 
        if madeDebugLog: debugLog("empty line, skip")
        continue #跳过这行
    
    #mega尚未被解析成torrent信息，无文件列表 ->进度为 n/a ,
    #如果已经完成了就不用去管了
    if parts[1]!='100%' and parts[1]!='n/a': 
        #获得hash先
        s_hash = seedHash(seedId)
        if not recordInLog(s_hash, hashlogs): #查找确认日志中是否已经有此hash，没有则处理, 包括了无效hash '' 的处理
            
            #文件列表
            p_filelist = subprocess.Popen('transmission-remote -t '+str(seedId)+' -f', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for file_row in p_filelist.stdout.readlines():
                #第一行不处理
                #只要提取第一部分作为Id就可以了
                fparts = file_row.split()
                fileId = fparts[0]
                if ':' in fileId: #如果不包含，那这行就不处理了，很可能是第一行
                    fileId = fileId[:-1] #去掉末尾的 :
                    doNotGet = False
                    if hitKey(file_row, keys):
                        if madeDebugLog: debugLog("hitkey["+file_row+"]")
                        doNotGet = True
                        
                    if not doNotGet and checkBlacklist and hitBlackList(file_row, blacklist):
                        if madeDebugLog: debugLog("hitblacklist["+file_row+"]")
                        doNotGet = True
                    
                    if doNotGet: #不下载这个文件
                        #transmission-remote -t seedID -G fileId
                        os.system('transmission-remote -t '+str(seedId)+' -G '+str(fileId))  #不下载的命令
                        #print("ok") #debug 未实现
                    
            
            if conf['upload_limited']>0 :  #0 时不做上行限速操作，单位 kb
                #transmission-remote -t seedID -u speedKB
                os.system('transmission-remote -t '+str(seedId)+' -u '+str(conf['upload_limited'])) #上传限速命令
                if madeDebugLog: debugLog("set uplimit["+seedId+":"+str(conf['upload_limited'])+"]")
                #print("ok") #debug 未实现
            
            #处理完全部文件，把这个hash添加到log里
            logHash(s_hash, logfile)
            #print("ok") #debug
                    
   
    #print line.strip() #debug
    





