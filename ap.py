#!/usr/bin/env python
import http.server
import hashlib
import requests
import sys
import re
import threading
from urllib.parse import urlparse

#/home/soungjin/ap/server.py

# =========================================
#import matplotlib.pyplot as plt
# =================================

hosts = {}   # 요청을 호출한 클라이언트 데이터

num = re.compile(r'([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)')
cache_qul = re.compile(r'cache=([0-9]{3})([0-9]{3})([0-9]{3})')
host_qul = re.compile(r'host=([a-zA-Z0-9_]+)')

class AP(http.server.BaseHTTPRequestHandler):

    def response(self,code,headers):#헤더를 보냄
        self.send_response(code) #응답코드
        for hk in headers:
            self.send_header(hk,headers[hk])
        self.end_headers() #헤더가 본문을 구분

    def print_file(self, url):
        data = requests.get(url)
        if data.status_code == 404:
            self.response(404,{'Content-type':'text/html'})
        roots = url.split('/')
        fname = roots[len(roots)-1] #파일명
        print(hashlib.md5(data.content).hexdigest(),end=" of :")
        self.response(200,{'Content-type':'application/octet-stream',"Content-Disposition":
                " attachment; filename="+fname,"Content-Transfer-Encoding":" binary",
                "Content-Length":sys.getsizeof(data.content)})
        self.wfile.write(data.content)

    def get_m4s(self,query,path_mpd,m4s):
        roots = m4s.split('/')
        del roots[len(roots)-1]
        roots = '/'.join(roots)+'/' 
        #==================================
        self.print_file(query + m4s)      # 다운로드 요청
    def do_GET(self):
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
            self.print_file('http://'+query+parsed_path.path)
        return None

    #def log_message(self, format, *args):
    #    return

port = int(input("in port :"))
server=http.server.HTTPServer(("",port),AP)
server.serve_forever()
