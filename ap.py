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
import matplotlib.pyplot as plt
# =========================================

db = {}     # 요청된 데이터를 캐싱하고 있는
hosts = {}   # 요청을 호출한 클라이언트 데이터
files = {}  # 요청 서버에 대응하는 파일군집 저장
lock = threading.Lock() # 스레드 락을 위한

root = os.getcwd() +"/"
cache = None
cach_dir = root + 'cache/'

# host = 'localhost'
host = ""
num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')

write_db = []
sstime = time.time() # system play

class MyHandler(http.server.BaseHTTPRequestHandler):


    def response(self,code,headers):#헤더를 보냄
        self.send_response(code) #응답코드
        for hk in headers:
            self.send_header(hk,headers[hk])
        self.end_headers() #헤더가 본문을 구분

    def is_cache_file(self,url):
        global db   
        if not url in db or not os.path.isfile(db[url]):
            return False
        return True
    
    def get_file(self,url):
        global db, write_db,sstime
        if not self.is_cache_file(url):
            try:
                s = time.time()
                data = requests.get(url, allow_redirects=True)
                if data.status_code == 404:
                    return False
                hname = hashlib.md5(data.content).hexdigest() #헤시 파일명
                with open(cach_dir +hname, 'wb') as f:
                    f.write(data.content)
                db[url] = cach_dir +hname
                write_db.append((s - sstime, time.time() - sstime,self.address_string(), url,"load data to server")) ############################
            except :
                return False
        return True
        
    def print_file(self, url):
        global db, write_db,sstime
        if not self.get_file(url):
            self.response(404,{'Content-type':'text/html'})
            return
        roots = url.split('/')
        fname = roots[len(roots)-1] #파일명
        s = time.time()
        self.response(200,{'Content-type':'application/octet-stream',"Content-Disposition":" attachment; filename="+fname,
            "Content-Transfer-Encoding":" binary","Content-Length":os.path.getsize(db[url])})
        with open(db[url],'rb') as f:
            i = f.read(1024)
            while(i):
                self.wfile.write(i)
                i = f.read(1024)
        write_db.append((s - sstime, time.time() - sstime,self.address_string(), url,"send Client data")) ############################

    def get_mpd(self,query,path):    # 호스트 / 경로로 mpd 데이터 가져오기
        global files
        if not self.get_file(query+path):
            return
        if query+path in files:  # in data
            self.print_file(query+path)
            return
        ft ='{urn:mpeg:dash:schema:mpd:2011}'
        tree = elemTree.parse(db[query+path])
        tree = tree.findall(ft + 'Period')[0]
        mpd = [[None]] # 싱크 조절을 위해 0번 인덱스 널값
        for adaptationset in tree.findall(ft + 'AdaptationSet'): # 타일 index
            reps = adaptationset.findall(ft + 'Representation')
            arr = {}
            sgtmp = adaptationset.find(ft+'SegmentTemplate')
            if sgtmp != None:# 1번째 전체 타일에 대한 파일
                fnames = num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]
                arr[fnames[0]]=[0,0,0,0]
                mpd[0].append('') # 이건 퀄리티
                mpd.append(arr)
                continue
            for rep in reps:# 퀄리티 index
                sgtmp = rep.find(ft+'SegmentTemplate')
                if sgtmp != None:
                    fnames = list(num.findall(sgtmp.attrib.get('media').replace("$Number$", "0"))[0]) # 
                    arr[fnames[0]]=[0,0,0,0]    # 클라이언트 최초 / 다운로드(맥시멈) / 현재 다운로드 되는 인덱스 / 다운로드 진행중인 스레드
            if len(arr.keys()):
                mpd[0].append('') # 이건 퀄리티
                mpd.append(arr) #{L:0,M:0,H:0}  #마지막으로 로드된 인덱스
        files[query+path] = mpd
        self.print_file(query+path)
        print("요청된 데이터(.mpd)를 처리함",query,path)

    def get_m4s_files(self,query,path_mpd,qul,tile,sindex,eindex):
        global files
        roots = path_mpd.split('/')
        del roots[len(roots)-1]
        roots = '/'.join(roots)+'/'
        
        data = files[query+path_mpd]
        print('다운로드 스레드 동작 : ',tile,sindex,eindex)
        for i in range(sindex,eindex+1):
            if qul != data[0][tile] or not data[tile][qul][3] and data[tile][qul][1] >= i:
                print('다운로드 스레드 중도 정지 : ',qul, data[0][tile],data[tile][qul][3], data[tile][qul][1])
                data[tile][qul][2] = -1         # 스레드
                break
            data[tile][qul][2] = i          # 다운로드 중임을 알림
            #print('Downloading....',query+roots+qul+'_dash_track'+str(tile)+'_'+str(i) + '.m4s')
            # print(str(tile)+'_'+str(i) + '.m4s',end=' |')
            url = query+roots+qul+'_dash_track'+str(tile)+'_'+str(i) + '.m4s'
            if not self.is_cache_file(url):
            
                if not self.get_file(url):
                
                    break # end of download
            
            data[tile][qul][1] = i          # 최신 다운로드 업데이트
            data[tile][qul][2] = -1         # 다운로드 왼료
        data[tile][qul][3] = -1             # 스레드 중지 알림
        print('다운로드 스레드 end : ',tile,data[tile][qul])

    def get_m4s(self,query,path_mpd,m4s):
        global files
        roots = m4s.split('/')
        fname = roots[len(roots)-1]
        del roots[len(roots)-1]
        roots = '/'.join(roots)+'/'

        fnames = num.findall(fname)[0] #실제 파일 이름 /조각
        fnames = (fnames[0],int(fnames[1]),int(fnames[2]))

        data = files[query+path_mpd]
        if data[0][fnames[1]] != fname[0]:# 타일퀄리티와 현재 퀄리티가 다른경우
            print("퀄리티 변경!",data[0][fnames[1]],"=>",fname[0])
            lock.acquire()# 락
            data[0][fnames[1]] = fname[0]   # 해당타일의 퀄리티 적용
            data[fnames[1]][fnames[0]][1] = data[fnames[1]][fnames[0]][2] = fnames[2]  # 해당하는 파일의 다운로드 알림
            if data[fnames[1]][fnames[0]][3]:           # 다운로드 인덱스가 진행중이면
                data[fnames[1]][fnames[0]][3] = 0      # 중지
            lock.release() #락 해제
            self.get_file(query + m4s)      # 다운로드 요청
            #data[fnames[1]][fnames[0]][3] = threading.Thread(target=self.get_file, args=(query + m4s))
        self.print_file(query+m4s)
        
        if cache != None:
            buffsize = int((cache[2] - cache[1]) / (len(data)-1))#버퍼 사이즈
            if buffsize:
                max = data[fnames[1]][fnames[0]][1] + buffsize
                if max <= fnames[2]+buffsize:
                    t = data[fnames[1]][fnames[0]][3] = threading.Thread(target=self.get_m4s_files, args=(query,path_mpd,fnames[0],fnames[1],data[fnames[1]][fnames[0]][1],max))
                    t.start()
                #print(query,path_mpd,fnames[0],fnames[1],data[fnames[1]][fnames[0]][1],max)
                    

    def do_GET(self):
        global hosts,cache,cache_qul
        parsed_path=urlparse(self.path)

        print("요청 수신",self.path)
        if parsed_path.path == '/':
            self.response(200,{'Content-type':'text/html'})
            self.wfile.write("올바르지 않은 접근".encode('utf-8'))
            return None
        else :
            query = parsed_path.query
            roots = parsed_path.path.split('/')
            fname = roots[len(roots)-1]
            del roots[len(roots)-1]
            roots = '/'.join(roots)+'/'

            # print("받은쿼리",query,fname)
            if not query:
                query = hosts[self.address_string()][0]
            elif cache_qul.match(query):
                cache = cache_qul.findall(query)[0]
                cache=(int(cache[0]),int(cache[1]),int(cache[2]))
                query = hosts[self.address_string()][0]
            else : # root file load
                hosts[self.address_string()] = [query,roots,fname]

            if fname[fname.rindex('.'):] =='.mpd':
                self.get_mpd('http://'+query,parsed_path.path)
            elif num.match(fname):  #m4s
                host = hosts[self.address_string()]
                self.get_m4s('http://'+query,host[1]+host[2],parsed_path.path)
            else :  #기타파일 그냥 저장
                # print(query,parsed_path.path)
                self.print_file('http://'+query+parsed_path.path)
        return None

def print_data():
    while 1:
        time.sleep(5)
        print(files)

s=http.server.HTTPServer((host,8080),MyHandler)
t=threading.Thread(target=print_data)
t.start()
print("server running!")
s.serve_forever()

