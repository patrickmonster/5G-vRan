var cluster = require('cluster');

cluster.schedulingPolicy = cluster.SCHED_NONE;
// cluster.schedulingPolicy = cluster.SCHED_RR

/* ======================================================================*/
const mpd_num = new RegExp("([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)");
const mpd_init = new RegExp("([a-zA-Z0-9_]+)_([a-zA-Z0-9_]+)_track([0-9]+)_init");//init.mp4 파일
const mpd_cache_qul = new RegExp("cache=([0-9]{3})([0-9]{3})([0-9]{3})");
const mpd_time = new RegExp("PT([0-9]+)H([0-9]+)M([0-9]+\.?[0-9]+)S");//총 재생시간
const mpd_qul = new RegExp("(\.+)MPD");
/* ======================================================================*/

if (cluster.isMaster){

	const url = require('url');
	const http = require("http");

	const init_track_size = 0;

	//xml 파서
	const parser = new require('xml2js').Parser();

	function Stack(size=0){
		this.data = [];
		this.top = 0;
		this.clearSize = (size<=10)?0:(size/30);
		this.push=function(element){
			this.data[this.top++]=element;
			if(size!=0 && size <= this.top)
				for(var i=0; i < this.clearSize;i++){
					this.top--;
					this.data.shift();
				}
			return this.top;
		}
		this.get=function(i){if(this.top >= i)return this.data[i];return false};
		this.pop=function(){if(this.top)return this.data[--this.top];else return 0};
		this.peek=function(){return this.data[this.top-1]};
		this.indexOf=function(s){
			var i = this.data.indexOf(s);
			if(i == undefined)return -1;
			return i;
		};
		this.length=function(){return this.top};
		this.clear=function(){this.top = 0;this.data.length=0};
		this.all=function(a,l){l=[];for(a=0;a<this.top;a++)l.push(this.data[a]);return l};
	}

	const cache_size = 1000;
	const files = {"roots":new Stack(cache_size),"datas":new Stack(cache_size)};
	const mpds = {};//mpd 데이터
	const none_data = new Stack();

	function reservation_init(worker,mpd,host){
		var l = [host];
		for (var i of mpd)
			if(!i.hasOwnProperty("name"))
				l.push(i.initialization);
		console.log(mpds[host.split('/')[0]].track,l[1]);
		if (mpds[host.split('/')[0]].track.indexOf(l[1]) != -1)
			return;
		if (l.length > 1)
			mpds[host.split('/')[0]].track.push(l[1]);
		worker.send({"pid":worker.process.pid,"event":"gets","data":l,"key":l[1]});
		console.log(l[1],"트랙 일괄 다운로드 예약(init)"); 
	}

	function receve_file(target,data){
		if (has_cache(target)!= -1)return;
		files.roots.push(target);
		files.datas.push(data);
	}

	//클러스터 통신용
	function onMessage(message) {
		if(message.event=="files"){//mpd 파일
			console.log(message.data.length,"수신파일");
			for (var file of message.data){
				if(file.data != false){
					file.data = Buffer.from(file.data);
					receve_file(file.target,file);
				}else if (none_data.indexOf(data.target)== -1)
					none_data.push(file.target);//없는데이터
			}
			var data = message.data[0];
			var host = data.target.substring(7).split("/");
			if (message.hasOwnProperty("key"))
				var i = mpds[host[0]].track.indexOf(message.key);
				if(i != -1){
					mpds[host[0]].track.splice(i,1);
					console.log(i,"파일 다운로드 완료(1)",message.key);
				}
			console.log("파일이 추가됨!" , message.data[0].name,"포함 총",message.data.length,"개의 파일");
		}else if(message.event=="file"){//mpd 파일
			var data = message.data;
			if(data.data != false){
				data.data = Buffer.from(message.data.data);
				receve_file(data.target,data);
			}else if (none_data.indexOf(data.target)== -1)
					none_data.push(data.target);//없는데이터
			var host = data.target.substring(7).split("/");
			var option = mpd_num.exec(data.target);
			
			if (message.hasOwnProperty("key"))
				var i = mpds[host[0]].track.indexOf(message.key);
				if(i != -1){
					mpds[host[0]].track.splice(i,1);
					console.log(i,"파일 다운로드 완료(2)",message.key);
				}
			if (/(\.mpd)$/i.test(data.target))
				if(!mpds[host[0]].hasOwnProperty(host.slice(1,host.length-1).join("/"))){
					parser.parseString(data.data,function(err,result){
						var mpd = [],option={};
						var period = result.MPD.Period[0];// period
						var worker = mpds[host[0]].worker;// 예약용
		
						option.name = host[host.length-1];
						option.duration = mpd_time.exec(period.$.duration);
						// option.duration = option.duration.slice(1,option.duration.length-1);
						option.length = period.AdaptationSet.length;// 트랙 길이
						option.cache = [0,0,0];
						
						mpd.push(option);
						console.log("===================================================");
						for(var i=0;i<option.length;i++){
							var arr = {};
							var adaptationset = period.AdaptationSet[i];
							var SegmentTemplate = adaptationset.SegmentTemplate[0];
							arr.media = SegmentTemplate.$.media;//H_dash_track1_$Number$.m4s
							arr.initialization = SegmentTemplate.$.initialization;//init.mp4 파일
							
							//사전예약
							arr.duration = SegmentTemplate.$.duration;//시간
							arr.frameRate = adaptationset.Representation[0].$.frameRate;//
							arr.bandwidth = adaptationset.Representation[0].$.bandwidth;//밴드위드
							arr.id = adaptationset.Representation[0].$.id;
							mpd.push(arr);
						}
						console.log(host.slice(1,host.length-1).join("/"));
						console.log(mpd.length);
						mpds[host[0]][host.slice(1,host.length-1).join("/")] = mpd;
						
						// 예약 다운로드
						reservation_init(worker,mpd,host.slice(0,host.length-1).join("/"));
					});
				}else {
					// 예약 다운로드
					reservation_init(mpds[host[0]].worker,mpds[host[0]][host.slice(1,host.length-1).join("/")],host.slice(0,host.length-1).join("/"));
				}
		}
	}

	function has_cache(target){
		return files.roots.indexOf(target);
	}

	function get_cache(index){
		return files.datas.get(index);
	}

	function load_list(host_root,is_get=false){
		////////////////////////////////////////////////////////////////////////////////////
		//트랙 다운로드
		var option = mpd_num.exec(host_root[host_root.length-1]); //파일 명
		var mpd_file = mpds[host_root[0]][host_root.slice(1,host_root.length-1).join("/")];
		var cache = mpd_file[0].cache;
		var max_buffer = Number(option[3]) + (cache[2] - cache[1]) / mpd_file[0].length;
		var worker = mpds[host_root[0]].worker;
		//option[1]+"_dash_track1_"+j - 검열트렉
		for(var j=Number(option[3]);j<max_buffer;j++){
			var track = option[1]+"_dash_track1_"+j+".m4s";
			var l = [host_root.slice(0,host_root.length-1).join("/")];
			for(var i=1;i<=mpds[host_root[0]][host_root.slice(1,host_root.length-1).join("/")][0].length;i++){
				var file = option[1]+"_dash_track"+i+"_"+j+".m4s";
				if (has_cache(host_root.slice(0,host_root.length-1).join("/")+"/"+file)!= -1 || mpds[host_root[0]].track.indexOf(file) != -1){
					continue;
				}
				l.push(file);
			}
			if(mpds[host_root[0]].track.indexOf(track)!= -1)
				continue;//이미 예액된 트렉은 넘어감
			if(none_data.indexOf(["http:/",host_root.slice(0,host_root.length-1).join("/"),track].join("/"))!=-1)
				continue;//찾을수 없는 데이터

			if (has_cache(["http:/",host_root.slice(0,host_root.length-1).join("/"),track].join("/")) != -1)
				continue;//이미 캐싱된 데이터
			worker.send({"pid":worker.process.pid,"event":is_get?"gets":"pushs","data":l,"key":l[1]});
			if (l.length > 1){
				mpds[host_root[0]].track.push(track);
				console.log("이벤트 등록 : "+l.length,track);
			}
		}
	}

	// 302 응답 처리
	function location(response, host){
		response.writeHead(302,{"Location": ["http:/",host.slice(host.length)].join("/")});
		response.end();
	}

	// 매인 다운로드 처리 함수
	function do_GET(response,pathname){
		const host = pathname.substring(1).split("/");// 타겟 호스
		var target = "http:/" +pathname;

		if (!mpds.hasOwnProperty(host[0])){
			var worker = cluster.fork();//워커 생성부분 - 1호스트 1워커
			worker.on('message', onMessage);//이벤트 등록
			mpds[host[0]] = {"worker":worker,"track":[]};
			console.log("워커생성 :",worker.process.pid);
		} 
		if(!/(\.m4s|\.mp4|\.mpd)$/i.test(host[host.length-1])){// 원하는 처리가 안됨
			location(response,host);
			return;
		}
		if (/(\.mp4)$/i.test(host[host.length-1]) || mpds[host[0]].hasOwnProperty(host.slice(1,host.length-1).join("/")) ){
			//initialization
			var index = 0;
			var root = host.slice(1,host.length-1).join("/");
			for (var i=1;i<mpds[host[0]][root].length;i++){
				var item = mpds[host[0]][root][i];
				if (item.hasOwnProperty("initialization") || item.initialization == host[host.length-1]){
					index = i;
					break;
				}
			}
			if (index == 0){	
				console.log(host,302,"처리함");
				location(response,host);
				return;
			}
		}
		var index = files.roots.indexOf(target);
		if(index==-1){// 찾을 수 없을때
			if(none_data.indexOf(target)!=-1){//찾을수 없는 데이터
				response.writeHead(404);
				response.end();
				return;
			}

			var worker = mpds[host[0]].worker;
			if(/(\.m4s)$/i.test(host[host.length-1])){
				var option = mpd_num.exec(host[host.length-1]);
				if(option[2]=='1'){//1타일일경우
					if(mpds[host[0]].track.indexOf(host[host.length-1]) == -1){
						var l = [host.slice(0,host.length-1).join("/")];

						for(var i=1;i<=mpds[host[0]][host.slice(1,host.length-1).join("/")][0].length;i++){
							var file = option[1]+"_dash_track"+i+"_"+option[3]+".m4s"
							if (has_cache(host.slice(0,host.length-1).join("/")+"/"+file) != -1 || mpds[host[0]].track.indexOf(file) != -1)continue;
							l.push(file);
						}
						worker.send({"pid":worker.process.pid,"event":"gets","data":l,"key":l[1]});
						console.log(option[3],"트랙 일괄 다운로드 예약",l[1]);
					}
					load_list(host);
				}
			}else{//m4s 가 아닌 외의 파일
				worker.send({"pid":worker.process.pid,"event":"push","data":[host.slice(0,host.length-1).join("/"),host[host.length-1]],"key":host[host.length-1]});
			}
			response.writeHead(202);
			response.end();
			return;
		}else{//찾았어
			var data = get_cache(index);// 캐싱데이터 불러오기
			if (data == false || data.data == false){
				response.writeHead(404);
				response.end();
			}else {
				sendFile(response,data);
				if(/(\.m4s)$/i.test(host[host.length-1]))//트렉 일괄다운로드
					load_list(host);
			}
		}
	}

	function setCache(pathname,qury){
		var hosts = pathname.substring(1).split("/");// 타겟 호스트
		var host = hosts[0], roots = hosts.slice(1,hosts.length-1).join("/");
		if(!mpds.hasOwnProperty(host) || !mpds[host].hasOwnProperty(roots)){
			return;
		}
		var option = mpd_cache_qul.exec(qury);
		mpds[host][roots][0].cache[0] = Number(option[1]);
		mpds[host][roots][0].cache[1] = Number(option[2]);
		mpds[host][roots][0].cache[2] = Number(option[3]);
	}

	function sendFile(response, option){//데이터 전송부
		try{
			response.writeHead(200,{'Content-type':'application/octet-stream',"Content-Disposition":
				" attachment; filename="+option.name,"Content-Transfer-Encoding":" binary",
				"Content-Length":option.length});
			response.end(option.data);
		}catch (e){
			console.log(option,e);
			response.writeHead(400);
			response.end();
		}
	}
	
	http.createServer((request,response)=>{
		const urls = url.parse(request.url);
		//method / headers / httpVersion/ url
		if(urls.pathname == "/favicon.ico"){
			response.writeHead(404);
			response.end();
			return;
		}else if(urls.pathname == "/"){
			response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
			response.write("<title>5GRan</title>");
			response.write("<h1>5GRan</h1>");
			for (var i in mpds){
				response.write("<br><h2>"+i+"</h2>");
				for (var j in mpds[i]){
					if (j=="worker")
						continue;
					if(j=='track'){
						response.write("<h2>"+j+"</h2>["+mpds[i][j].length+"]");
						response.write(JSON.stringify(mpds[i][j]));
						continue;
					}
					response.write("<h2>"+j+"</h2>");
					response.write("<ul>");
					for(var k of mpds[i][j])
						response.write("<li>"+ JSON.stringify(k) + "</li>");
					response.write("</ul>");
				}
			}

			response.write("<h2>caching files</h2><ul style='height:500px;width:500px;overflow:scroll'>");
			for(var i = 0; i < files.roots.length();i++)
				response.write("<li>"+ files.roots.get(i) + "</li>");
			response.write("</ul>" + files.roots.length() + "/" + cache_size + "|" +files.roots.clearSize);

			response.write("<h2>None files</h2><ul style='height:500px;width:500px;overflow:scroll'>");
			for(var i = 0; i < none_data.length();i++)
				response.write("<li>"+ none_data.get(i) + "</li>");
			response.write("</ul>" + none_data.length() + "/");
			response.end("<script>setTimeout(()=>{location.reload()},5*1000);</script>");
			return;
		}
		do_GET(response,urls.pathname);
		if(urls.query && mpd_cache_qul.test(urls.query))setCache(urls.pathname,urls.query);
	}).listen(8080,()=>{
	  console.log("서버 on");
	});
}
// 보조 프로세서
//=============================================================================================//
if (cluster.isWorker) {
	const request = require('sync-request');
	const queue = [];//다운로드 예약 목록
	process.on("message",function(message){
		if (message.pid != process.pid)return;// 해당하는 프로세서가 아님
		if (message.event == "push"){//예약처리
			queue.push(message.data);//host/name
		}else if(message.event == "get"){// 우선처리
			var i = queue.indexOf(message.data);
			if (i != -1)queue.splice(i,1);// 원소 제거
			process.send({"pid":process.pid,"event":"file","data":get_file(message.data[0],message.data[1]),"key":message.key});
		}else if(message.event == "gets"){// 우선처리
			var l = [];
			for(var j=1;j<message.data.length;j++){
				var i = queue.indexOf([message.data[0],message.data[j]]);
				if (i != -1)queue.splice(i,1);// 원소 제거
				l.push(get_file(message.data[0],message.data[j]))
			}
			process.send({"pid":process.pid,"event":"files","data":l,"key":message.key});
		}else if(message.event == "pushs"){// 예약처리
			for(var j=1;j<message.data.length;j++){
				var data = [message.data[0],message.data[j]];
				if (queue.indexOf(data) != -1)continue;
				queue.push(data);
			}
		}
	});

	setInterval(function(){ // 다운로드 큐 처리용 루퍼
		if(queue.length <= 0)return;
		var arg = queue.shift();// 받을 데이터
		process.send({"pid":process.pid,"event":"file","data":get_file(arg[0],arg[1]),"key":arg[1]});
	});

  console.log("워커 프로세서 (",process.pid,") 동작!")

  /*
  * 파일을 로드하여 데이터 저장
  */
	function get_file(host,name) {
		var target = ["http:/",host,name].join('/');
		var data;
		try {
			data = request('GET',target);
		} catch (e) {return {'target':target,data:false};}
		if(data.statusCode == 404)
			return {'target':target,data:false};
		return {
			'name':name,
			'length':data.body.byteLength,
			'data':data.body,
			'target':target,
		};
	}
}
