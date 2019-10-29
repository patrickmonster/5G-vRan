#!/usr/bin/env python
import http.server
import sys
import requests
import xml.etree.ElementTree as elemTree
import re
import time
from urllib.parse import urlparse

# =========================================
#/home/soungjin/ap/server.py
# =========================================

def get_duration_time(duration):
    time = [int(float(x)) for x in duration]
    i = 0
    for t in range(len(time)):
        i = i * 60 + time[t]
    return i

hosts = {}   # 요청을 호출한 클라이언트 데이터
files = {}  # 요청 서버에 대응하는 파일군집 저장

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')
mpd_qul = re.compile(r'(.+)MPD')

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
            else : # root file load
                hosts[self.address_string()] = [query,roots,fname,None]
            self.print_file('http://'+query + parsed_path.path)

port = int(input("in port :"))
server=http.server.HTTPServer(("",port),AP)
server.serve_forever()
