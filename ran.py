#!/usr/bin/env python
#url = "http://203.247.232.147:8080/rb.10x8/rb.mpd?203.247.232.146"
#url = 'http://549.ipdisk.co.kr/gpac/rb.10x8/rb.mpd'

import http.server
import sys
import xml.etree.ElementTree as elemTree
import re
import time
import os
import gc
import requests
import threading
import hashlib
from urllib.parse import urlparse
from memqueue import MemQueue, Module
from log import Log

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')#H_dash_track16_init
init_f = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_init')#H_dash_track16_init
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')
mpd_time = re.compile(r'PT([0-9]+)H([0-9]+)M([0-9]+\.?[0-9]+)S')
mpd_qul = re.compile(r'(.+)MPD')

root = os.getcwd() +"/"
cach_dir = root + 'cache/'


def get_duration_time(duration):
    time = [int(float(x)) for x in duration]
    i = 0
    for t in range(len(time)):
        i = i * 60 + time[t]
    return i

l = Log()

def timing(f):
    def wrap(*args):
        s = args[0]
        time1 = time.time()
        ret = f(*args)
        time2 = time.time()
        if ret == False:
            l.log([f.__name__,s.client_address[0],s.client_address[1],'함수 실행시간',(time2-time1)*1000.0])
            # print('%s 함수 실행시간 %0.3fms' % (f.__name__, (time2-time1)*1000.0))
        else :
            if ret:
                h = str(hashlib.md5(ret).hexdigest())
            else:
                h = "None"
            l.log([f.__name__,s.client_address[0],s.client_address[1],'함수 실행시간',(time2-time1)*1000.0,h])
            # print('%s 함수 실행시간 %0.3fms [%s]' %(f.__name__, (time2-time1)*1000.0,h))
        return ret
    return wrap

class AP(http.server.BaseHTTPRequestHandler):
    #protocol_version = "HTTP/1.1"
    files = {}
    module = Module(10000) # m4s 파일 전용
    module_file = Module(50)# 용량이 큰 데이터?
    cl = threading.Lock() # mpd 락

    def clean_mem(self):
        print("메모리 해제!(종료 대기...)")
        self.module.clean_mem()
        self.module_file.clean_mem()
        for i in self.files:
            del self.files[i]
        gc.collect()
        print("메모리 해제완료!")
        l.log("메모리 해제(프로그램 종료)")
    
    def response(self,code,headers):
        self.send_response(code)
        for hk in headers:
            self.send_header(hk,headers[hk])
        self.end_headers()
    
    @timing
    def print_data(self, name, data,is_keep_alive=False):
        heads = {'Content-type':'application/octet-stream',"Content-Disposition":
                " attachment; filename="+name,"Content-Transfer-Encoding":" binary",
                "Content-Length":len(data)}
        if is_keep_alive:
            heads['connection'] = 'keep-alive'
        self.response(200,heads)
        try:
            self.wfile.write(data)
        except:
            pass
    
    @timing
    def get_file(self,url,is_m4s=False):#온니 모듈엑세스
        global caching
        if is_m4s:
            md = self.module
        else:
            md = self.module_file
        if not caching:# 무조건 다운
            return md.get_file(url,None,caching)
        data = md.get_cache(url)#캐시 확인
        if data:
            return data
        return md.get_file(url,None,caching)# 직접다운
    
    def get_m4s(self,host,root,m4s):
        data = self.files[host]['_cache'].priority('http://' + host + root + m4s)
        #print("요청 - 데이터 모음(가정)", cache)
        fnames =  num.findall(m4s)[0] #실제 파일 이름 /조각
        #fnames = (fnames[0],int(fnames[1]),int(fnames[2]))# 파일명, 타일번호, index
        if int(fnames[1]) != 1:
            return data
        #==================================
        cache = self.files[host][root][0] # 퀄리티 서치
        #self.files[host][root][int(fnames[0])][1] = int(fnames[2]) # 현재 다운로드 된 캐시 인덱스 적용
        size = len(self.files[host][root])
        pre_buffsize = self.files[host][root][1][fnames[0]][1] # 최근의 다운받은 버퍼
        max_buffsize = int(fnames[2]) + int((cache[2] - cache[1]) / (size-1))#버퍼 사이즈(서버측))
        if max_buffsize > cache[0]:
            max_buffsize = cache[0]
        for i in self.files[host][root]:
            if type(i) == list:
                continue
            if not i[fnames[0]] or i[fnames[0]][1] < max_buffsize :
                i[fnames[0]] = [int(fnames[2]), max_buffsize]# 등록 (클라이언트 요청 버퍼 인덱스, 예상 최대 버퍼 크기)
        # print(max_buffsize)
        url = 'http://' +host + root + fnames[0] + '_dash_track'
        print("캐싱 추가",url,pre_buffsize+1, max_buffsize+1)
        for i in range(pre_buffsize+1, max_buffsize+1):
            index_m4s = '_' +str(i)+'.m4s'
            for i in range(1,len(self.files[host][root])):
                self.files[host]['_cache'].enqueue(url + str(i)+index_m4s)
        return data
    @timing
    def get_mpd(self,host,path,mpd):    # 호스트 / 경로로 mpd 데이터 가져오기
        url = "http://"+host + path + mpd# host(http://ip) + path(gpac/rb.10x8/rb.mpd)
        with self.cl:# 권한 획득전까지 대기
            try:
                if self.files[host]:
                    pass
            except :
                self.files[host] = {'_cache':MemQueue(self.module.get_file)}#get_file"
            data = self.get_file(url)
            try:
                if self.files[host][path]:
                    print("요청된 데이터(.mpd)를 전송",host,path)
            except KeyError:
                #data = self.files[host]['_cache'].priority(url)
                print("요청",host,path)
                data = self.get_file(url)
                tree = elemTree.fromstring(data)
                mpd = [[int(get_duration_time(mpd_time.findall(tree.attrib.get("mediaPresentationDuration"))[0])/
                                get_duration_time(mpd_time.findall(tree.attrib.get("maxSegmentDuration"))[0])),0,0]]
                                # 데이터 개수, 캐싱 진행, 캐싱 최대
                # mpd 0번지에 최대 파일 개수
                get_duration_time(mpd_time.findall(tree.attrib.get("maxSegmentDuration"))[0])
                get_duration_time(mpd_time.findall(tree.attrib.get("mediaPresentationDuration"))[0])
                ft = mpd_qul.findall(tree.tag)[0]# xml 파일 형식상 붙혀주는것
                tree = tree.findall(ft + 'Period')[0]
                for adaptationset in tree.findall(ft + 'AdaptationSet'): # 타일 index
                    arr = {}
                    sgtmp = adaptationset.find(ft+'SegmentTemplate')
                    if sgtmp != None:# 1번째 전체 타일에 대한 파일
                        fnames = num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]
                        arr[fnames[0]]=[0,0]
                    else:
                        reps = adaptationset.findall(ft + 'Representation')
                        for rep in reps:# 퀄리티 index
                            sgtmp = rep.find(ft+'SegmentTemplate')# 최근에 또 바꿔서 한번 더 고려해야 함,.
                            if sgtmp != None:
                                fnames = list(num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]) # 
                                arr[fnames[0]]=[0,0]    # 클라이언트 마지막 요청 / 다운로드 예정 맥시멈
                    if len(arr.keys()):
                        mpd.append(arr) #{L:0,M:0,H:0} # 1 타일
                self.files[host][path] = mpd
                print("요청된 데이터(.mpd)를 처리함",host,path,self.files[host][path])
        return data

    @timing
    def do_GET(self):
        global cache_qul,caching, num,init_f
        parsed_path=urlparse(self.path)
        if parsed_path.path == '/':
            self.response(200,{'Content-type':'text/html'})
            self.wfile.write("Not found Service!".encode('utf-8'))
            return None
        if parsed_path.path == '/exit':
            print("서버가 종료됩니다....")
            self.response(200,{'Content-type':'text/html'})
            self.wfile.write("End of Service!".encode('utf-8'))
            server.server_close()
        else :
            query = parsed_path.query # 쿼리
            roots = parsed_path.path[1:].split('/')
            host = roots.pop(0)
            fname = roots.pop() # 요청 파일
            roots = '/'.join(roots)+'/'# 요청 링크
            #print(query,roots,host,fname) #  gpac/rb.10x8/ 549.ipdisk.co.kr rb.mpd
            if not caching:
                data = self.get_file('http://' + host + "/" + roots + fname)
                self.print_data(fname,data)
                return False
            elif fname[fname.rindex('.'):] == '.mpd':
                data = self.get_mpd(host, "/" + roots, fname)
                self.print_data(fname,data)
                return False
            elif num.match(fname):#m4s
                data = self.get_m4s(host, "/" + roots, fname)
            elif init_f.match(fname):#init
                data = self.get_file('http://' + host + "/" + roots + fname)
            else :
                data = self.get_file('http://' + host + "/" + roots + fname)
            if cache_qul.match(query):# cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')
                cache = cache_qul.findall(query)[0]
                self.files[host]['/'+roots][0][1] = int(cache[1])# self.files[host][root][int(fnames[1])][fnames[0]]
                if not self.files[host]['/'+roots][0][2] or self.files[host]['/'+roots][0][2] < int(cache[2]):
                    self.files[host]['/'+roots][0][2] = int(cache[2])
            self.print_data(fname,data)
        return False
    
    def log_message(self, format, *args):
        return
    
#port = int(input("in port :"))
port = 8080
caching = True
if len(sys.argv) > 1:
    caching = False
print("Start service to port:",port," isCache:",caching)
server=http.server.HTTPServer(("",port),AP)
try:
    server.serve_forever()
except:
    pass
print("서버가 종료됨")
server.RequestHandlerClass.clean_mem(server.RequestHandlerClass)
