#!/usr/bin/env python
import requests
import hashlib
import xml.etree.ElementTree as elemTree
import re
import os
import time
import threading

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
mpd_qul = re.compile(r'(.+)MPD')
mpd_time = re.compile(r'PT([0-9]+)H([0-9]+)M([0-9]+\.?[0-9]+)S')
qury_qul = re.compile(r'(.+)\?(.+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')

# os.getpid()

root = os.getcwd() +"/"
cach_dir = root + 'cache/'

class Log():

    def __init__(self):
        self.fname = time.strftime('%Y-%m-%d_%H_%M_%S', time.localtime(time.time())) + "_%d" %(os.getpid())
        self.dir = os.getcwd() +"/logs/"
        if not(os.path.isdir(self.dir)):
            os.makedirs(os.path.join(self.dir))
        self.f = open(self.dir + self.fname,'a')

    def __del__(self):
        print("%s 파일을 로그로 저장"%(self.fname))
        self.f.close()

    def log(self,str,end="\n"):
        self.f.write(str+end)



mpd = [[None]]
l = Log()

def timing(f):
    def wrap(*args):
        time1 = time.time()
        ret = f(*args)
        time2 = time.time()
        if ret == False:
            pass
        elif ret == True:
            log('%s 함수 실행시간 %0.3fms' % (f.__name__, (time2-time1)*1000.0))
        else :
            log('%s 함수 실행시간 %0.3fms [%s]' %(f.__name__, (time2-time1)*1000.0,hashlib.md5(ret).hexdigest()))
        return ret
    return wrap

def log(str,end="\n"):
    global l
    e = end
    l.log(str,end=e)

@timing
def get_file(url,tout=None):
    data = requests.get(url,timeout=tout)
    while data.status_code == 202:
        time.sleep(1)
        data = requests.get(url,timeout=tout)
    if data.status_code == 404:
        return False
    #log(hashlib.md5(data.content).hexdigest()) #헤시 파일명
    return data.content

def get_duration_time(duration):
    time = [int(float(x)) for x in duration]
    i = 0
    for t in range(len(time)):
        i = i * 60 + time[t]
    return i

@timing
def get_mpd(url):    # 호스트 / 경로로 mpd 데이터 가져오기
    global mpd
    f = get_file(url)
    if not f:
        return False
    tree = elemTree.fromstring(f)
    if mpd_qul.match(tree.tag):
        ft = mpd_qul.findall(tree.tag)[0]
    else:
        ft = ""
    mpd[0][0] = [get_duration_time(mpd_time.findall(tree.attrib.get("maxSegmentDuration"))[0]),get_duration_time(mpd_time.findall(tree.attrib.get("mediaPresentationDuration"))[0])]
    print(mpd_time.findall(tree.attrib.get("mediaPresentationDuration"))[0])
    tree = tree.findall(ft + 'Period')[0]
    for adaptationset in tree.findall(ft + 'AdaptationSet'): # 타일 index
        reps = adaptationset.findall(ft + 'Representation')
        arr = {}
        sgtmp = adaptationset.find(ft+'SegmentTemplate')
        if sgtmp != None:# 1번째 전체 타일에 대한 파일
            fnames = num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]
            arr[fnames[0]]=[0,0]
            arr["init"] = sgtmp.get("initialization")
            mpd[0].append('') # 이건 퀄리티
            mpd.append(arr)
            continue
        for rep in reps:# 퀄리티 index
            sgtmp = rep.find(ft+'SegmentTemplate')# 최근에 또 바꿔서 한번 더 고려해야 함,.
            if sgtmp != None:
                fnames = list(num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]) #
                arr[fnames[0]]=[0,0]    # 클라이언트 마지막 요청 / 다운로드 예정 맥시멈
                arr["init"] = sgtmp.get("initialization")
        if len(arr.keys()):
            mpd[0].append('') # 이건 퀄리티
            mpd.append(arr) #{L:0,M:0,H:0} # 1 타일
    return True

def get_m4s(url):
    global mpd
    roots = url.split('/')
    del roots[len(roots)-1]
    roots = '/'.join(roots)+'/'
    if qury_qul.match(url):
        print(qury_qul.findall(url)[0])
        qury = [i for i in qury_qul.findall(url)[0]][1] # 쿼리문 가져오기
    else :
        qury = ""
    time1 = time.time()
    for m in range(1,len(mpd)):
        hashlib.md5(get_file(roots + mpd[m]['init'])).hexdigest()
    time2 = time.time()
    log('init 파일 로드 %0.3fms' % ((time2-time1)*1000.0))

    index = 1
    cache_now = 0
    cache_ac = 2
    cache_max = 10
    #while 1:
    time1 = time.time()
    while 1:
        now = int((time.time()-time1)*1000.0) # 프로그램 진행시간
        st = int(now / mpd[0][0][0] / 1000) # 현재 재생중잉어야하는 인덱스
        if cache_now < cache_ac:
            for i in range(index+cache_now,index+cache_ac):
                for j in range(1,len(mpd)):
                    k = [m for m in mpd[j].keys()][-2]
                    length = len(mpd) -1
                    url =roots+k+'_dash_track'+str(j)+'_'+str(i) + '.m4s'
                    url+="?cache=%03d%03d%03d"%(cache_now * length,cache_ac * length,cache_max * length)
                    get_file(url)
            cache_now = cache_ac
        for i in range(index,st+1):
            print("play to %d..." %index)
            #print(now,st)
            index+=1 # 영상재생
            if cache_now > 0:
                cache_now-=1 # 캐시 비우기
                print("[%d] Now play time : %d/%d"%(index,now/1000,cache_now),end="\tClear cache\n")
            else :
                print("[%d] Now play time : %d"%(index,now/1000),end="\tNone  cache\n")

        if now/1000 > mpd[0][0][1]:
            print("플레이어 종료")
            break
    time2 = time.time()
    log('미디어 플레이타임 %0.3fms' % ((time2-time1)*1000.0))

    return True


process_s = time.time()
# url = input("url>")
url = "http://10.42.0.1:8080/203.247.240.208/rb.10x8/rb.mpd"
if get_mpd(url):
    #print(mpd)
    get_m4s(url)
else :
    print("No get mpd data!")
process_e = time.time()
l.log('미디어 플레이타임 %0.3fms' % ((process_e-process_s)*1000.0))
