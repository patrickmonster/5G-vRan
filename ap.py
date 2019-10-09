#!/usr/bin/env python
import http.server
import os 
import hashlib
import requests
import xml.etree.ElementTree as elemTree
import re
import threading
import time
from urllib.parse import urlparse
from datetime import datetime
from urllib.parse import urlparse

#/home/soungjin/ap/server.py

# =========================================
#import matplotlib.pyplot as plt
# =========================================

class DownloadQueue(list): # 1 호스트 대응 url
    
    def __init__(self):
        self.is_run = False
        self.thread = 0
        self.priority = 0 # 우선처리 포인터
        self.prioritys = []
        self._sleept = 0
        self.callback = None
        
    def create_thread(self,timeout=1,func = None):
        if self.is_run:
            return
        self.thread  = threading.Thread(target=self.run)
        if func:
            self.callback = func
        self.is_run = True
        self.thread.start()
        return self
    
    def enqueue(self,obj):
        self.append(obj)
        if not self.is_run:
            self.create_thread()

    def push(self,obj,func):# 우선처리 삽입
        self.insert(self.priority,obj)
        self.prioritys.append(func) # 동시처리
        self.priority+=1
        if not self.is_run:
            self.create_thread()

    def dequeue(self):
        return self.pop(0)

    def clear(self):
        while len(self) > 0 :
            self.pop()
        self.priority=0

    def is_empty(self):
        if not self:
            return True
        else:
            return False

    def peek(self):
        return self[0]
    
    def run(self):# callback
        while self.is_run:
            if self.is_empty():# 30초동안 반응이 없으면 스레드를 죽임
                if not self._sleept:
                    self._sleept = time.time()
                    continue
                if time.time() - self._sleept > 1000 * 30:
                    break
                continue
            self._sleept = 0
            o = self.dequeue()# 첫 항목
            if not get_file(o,tout=0.1):
                self.is_run = False
                self.clear()
                break
            #func(o) # callboack to obj
            if self.priority > 0: #우선순위 처리작업
                if self.callback:
                    self.callback(o)
                self.priority-=1

db = {}     # 요청된 데이터를 캐싱하고 있는
root = os.getcwd() +"/"
cach_dir = root + 'cache/'

def is_cache_file(url):
    global db
    if not url in db or not os.path.isfile(db[url]):
        return False
    return db[url]

def get_file(url,tout=None):# 스레드로 호출되야 하지
    global db
    if not url in db or not os.path.isfile(db[url]):
        try:
            data = requests.get(url,timeout=tout)
            if data.status_code == 404:
                return False
            hname = hashlib.md5(data.content).hexdigest() #헤시 파일명
            with open(cach_dir +hname, 'wb') as f:
                f.write(data.content)
            db[url] = cach_dir + hname
        except :
            return False
    return db[url]


hosts = {}   # 요청을 호출한 클라이언트 데이터
files = {}  # 요청 서버에 대응하는 파일군집 저장
# lock = threading.Lock() # 스레드 락을 위한

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')



class AP(http.server.BaseHTTPRequestHandler):

    def response(self,code,headers):#헤더를 보냄
        self.send_response(code) #응답코드
        for hk in headers:
            self.send_header(hk,headers[hk])
        self.end_headers() #헤더가 본문을 구분


    def ondownload(self,obj):
        pass

    def print_file(self, url, is_down=True):
        f = is_cache_file(url)
        if not f and is_down:
            f = get_file(url)
            if not f: # 현재의 스레드로 다운로드 시도
                self.response(404,{'Content-type':'text/html'})
                return
        roots = url.split('/')
        fname = roots[len(roots)-1] #파일명
        self.response(200,{'Content-type':'application/octet-stream',"Content-Disposition":
                " attachment; filename="+fname,"Content-Transfer-Encoding":" binary",
                "Content-Length":os.path.getsize(f)})
        with open(f,'rb') as fr:
            i = fr.read(1024)
            while(i):
                self.wfile.write(i)
                i = fr.read(1024)

    def get_mpd(self,query,path):    # 호스트 / 경로로 mpd 데이터 가져오기
        global files
        f = is_cache_file(query+path)
        if not f:
            f = get_file(query+path)
            if not f:
                return
        if not query in files:
            files[query] = {'_cache':DownloadQueue().create_thread(self.ondownload)}
        ft ='{urn:mpeg:dash:schema:mpd:2011}'
        tree = elemTree.parse(f)
        tree = tree.findall(ft + 'Period')[0]
        mpd = [[None]] # 싱크 조절을 위해 0번 인덱스 널값
        for adaptationset in tree.findall(ft + 'AdaptationSet'): # 타일 index
            reps = adaptationset.findall(ft + 'Representation')
            arr = {}
            sgtmp = adaptationset.find(ft+'SegmentTemplate')
            if sgtmp != None:# 1번째 전체 타일에 대한 파일
                fnames = num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]
                arr[fnames[0]]=[0,0]
                mpd[0].append('') # 이건 퀄리티
                mpd.append(arr)
                continue
            for rep in reps:# 퀄리티 index
                sgtmp = rep.find(ft+'SegmentTemplate')# 최근에 또 바꿔서 한번 더 고려해야 함,.
                if sgtmp != None:
                    fnames = list(num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]) # 
                    arr[fnames[0]]=[0,0]    # 클라이언트 마지막 요청 / 다운로드 예정 맥시멈
            if len(arr.keys()):
                mpd[0].append('') # 이건 퀄리티
                mpd.append(arr) #{L:0,M:0,H:0} # 1 타일
        files[query][path] = mpd
        self.print_file(query+path)
        print("요청된 데이터(.mpd)를 처리함",query,path)

    # 안쓰는 함수
    def get_m4s_files(self,query,path_mpd,qul,tile):
        global files
        '''
        다중 다운로드 처리
        '''
        roots = path_mpd.split('/')
        del roots[len(roots)-1]
        roots = '/'.join(roots)+'/'
        
        data = files[query][path_mpd][tile][qul]
        for i in range(data[1],data[3]+1):
            if not data[4] and data[0] >= i:
                data[2] = -1         # 스레드
                break
            data[2] = i
            url = query+roots+qul+'_dash_track'+str(tile)+'_'+str(i) + '.m4s'
            files[query]["_cache"].enqueue(url) # 스레딩에 넣음
            data[1] = i          # 최신 다운로드 업데이트
    def change_buffer_size(self,max,client=0,src=None):
        if src:
            hosts[src][3]=[client,max]
        else :
            hosts[self.address_string()][3]=[client,max]

    def get_m4s(self,query,path_mpd,m4s):
        global files
        roots = m4s.split('/')
        fname = roots[len(roots)-1]
        del roots[len(roots)-1]
        roots = '/'.join(roots)+'/'

        fnames = num.findall(fname)[0] #실제 파일 이름 /조각
        fnames = (fnames[0],int(fnames[1]),int(fnames[2]))

        data = files[query][path_mpd][fnames[1]][fnames[0]]
        data[0] = fnames[2] # 실시간 요청데이터 적용
        #==================================
        self.print_file(query + m4s)      # 다운로드 요청

        if hosts[self.address_string()][3] != None:#캐시로딩중
            cache=hosts[self.address_string()][3]
            buffsize = int((cache[1] - cache[0]) / (len(files[query][path_mpd])-1))#버퍼 사이즈(서버측))
            if buffsize:
                max = fnames[2] + buffsize #지금 진행되어야 하는 서버측 버퍼크기 계산
                data[1] = max # 실시간 데이터에 맥스값 지정
                url = query+roots+fnames[0]+'_dash_track'+str(fnames[1])+'_'
                for i in range(data[0],data[1]):# 요청
                    files[query]['_cache'].enqueue(url +str(i)+'.m4s')

    def do_GET(self):
        global hosts,cache_qul
        parsed_path=urlparse(self.path)
        if parsed_path.path == '/':
            self.response(200,{'Content-type':'text/html'})
            self.wfile.write("Not found Service!".encode('utf-8'))
            return None
        else :
            query = parsed_path.query
            roots = parsed_path.path.split('/')
            fname = roots[len(roots)-1]
            del roots[len(roots)-1]
            roots = '/'.join(roots)+'/'
            if not query:
                query = hosts[self.address_string()][0]
            elif cache_qul.match(query):
                cache = cache_qul.findall(query)[0]
                if not hosts[self.address_string()][3]:
                    print("클라이언트 버퍼링 크기:",cache[0])
                    hosts[self.address_string()][3]=[int(cache[1]),int(cache[2])]
                elif int(cache[2]) != hosts[self.address_string()][3][1] or int(cache[1]) != hosts[self.address_string()][3][0]:
                    hosts[self.address_string()][3]=[int(cache[1]),int(cache[2])]
                query = hosts[self.address_string()][0]
            else : # root file load
                hosts[self.address_string()] = [query,roots,fname,None]
            if fname[fname.rindex('.'):] =='.mpd':
                self.get_mpd('http://'+query,parsed_path.path)
            elif num.match(fname):  #m4s
                host = hosts[self.address_string()]
                self.get_m4s('http://'+query,host[1]+host[2],parsed_path.path)
            else :  #기타파일 그냥 저장
                self.print_file('http://'+query+parsed_path.path)
        return None
    def clearThread(self,qury):
        print("stoped thread...",qury)
        #for i in range(1,len(files[qury])):

    def log_message(self, format, *args):
        return


def print_data():
    global hosts,files,server
    print("server running!")
    while 1:
        time.sleep(5)
        for i in files.keys():
            for j in files[i]:
                if j == "_cache":
                    print("캐시상태 (%s): %d"%(i,len(files[i][j])))
                    continue
                k = files[i][j]
                print(k[1],end="")
                print()
        print("]")

port = int(input("in port :"))
server=http.server.HTTPServer(("",port),AP)
t=threading.Thread(target=print_data)
t.start()
server.serve_forever()
