#!/usr/bin/env python
import http.server
import sys
import requests
import xml.etree.ElementTree as elemTree
import re
import threading
import time
from urllib.parse import urlparse

#/home/soungjin/ap/server.py

# =========================================
#import matplotlib.pyplot as plt
# =========================================

def get_duration_time(duration):
    time = [int(float(x)) for x in duration]
    i = 0
    for t in range(len(time)):
        i = i * 60 + time[t]
    return i

hosts = {}   # 요청을 호출한 클라이언트 데이터
files = {}  # 요청 서버에 대응하는 파일군집 저장
# lock = threading.Lock() # 스레드 락을 위한

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')
mpd_qul = re.compile(r'(.+)MPD')
#host_qul = re.compile(r'host=([a-zA-Z0-9_]+)')
#mpd_time = re.compile(r'PT([0-9]+)H([0-9]+)M([0-9]+\.?[0-9]+)S')

class AP(http.server.BaseHTTPRequestHandler):

    def response(self,code,headers):#헤더를 보냄
        self.send_response(code) #응답코드
        for hk in headers:
            self.send_header(hk,headers[hk])
        self.end_headers() #헤더가 본문을 구분

    def print_file(self, url, is_down=True):
        data = requests.get(url)
        roots = url.split('/')
        fname = roots[len(roots)-1] #파일명
        self.response(200,{'Content-type':'application/octet-stream',"Content-Disposition":
                " attachment; filename="+fname,"Content-Transfer-Encoding":" binary",
                "Content-Length":sys.getsizeof(data.content)})
        self.wfile.write(data.content)

    def get_mpd(self,query,path):    # 호스트 / 경로로 mpd 데이터 가져오기
        global files
        data = requests.get(query + path)
        if not data:
            print("처리에러!")
            self.print_file(query + path)
            return
        if not query in files:# 해당호스트에 데이터가 없으면
            files[query] = {"_lock": threading.Lock()}

        with files[query]["_lock"]:
            try:
                tree = elemTree.fromstring(data)
            except:
                tree = elemTree.fromstring(data.encode('UTF-8'))
            ft = mpd_qul.findall(tree.tag)[0]# xml 파일 형식상 붙혀주는것
            print(tree.attrib) #{'duration': 'PT0H3M15.000S'}
            mpd = [[None]]
            tree = tree.findall(ft + 'Period')[0]
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
        print("요청된 데이터(.mpd)를 처리함",query,path)

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
            self.print_file('http://'+query + parsed_path.path)

port = int(input("in port :"))
server=http.server.HTTPServer(("",port),AP)
server.serve_forever()
