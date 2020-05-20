const url = require('url');
const http = require("http");
const request = require('sync-request');

//xml 파서
const parser = new require('xml2js').Parser();

// const cluster = require('cluster');// 클러스터 스레딩
// cluster.schedulingPolicy=cluster.SCHED_RR; // 라운드 로빈 방식
// npm install http-proxy --save

cache_size = 500;

/* ======================================================================*/
const mpd_num = new RegExp("([a-zA-Z0-9_]+)_dash_track([0-9]+)_([0-9]+)");
// const mpd_init = new RegExp("([a-zA-Z0-9_]+)_dash_track([0-9]+)_init");//init.mp4 파일
const mpd_cache_qul = new RegExp("cache=([0-9]{3})([0-9]{3})([0-9]{3})");
const mpd_time = new RegExp("PT([0-9]+)H([0-9]+)M([0-9]+\.?[0-9]+)S");//총 재생시간
const mpd_qul = new RegExp("(\.+)MPD");
/* ======================================================================*/
function Stack(size=0){
	this.data = [];
	this.top = 0;
	var clearSize = (size<=10)?0:(size/10);
	this.push=function(element){
		this.data[this.top++]=element;
		if(size!=0 && size <= this.top)
			for(var i=0; i < clearSize;i++)
				this.pop();
		return this.top
	}
	this.get=function(i){if(this.data.length < i)return this.data[i];return 0};
	this.pop=function(){if(this.top)return this.data[--this.top];else return 0;};
	this.peek=function(){return this.data[this.top-1];};
	this.indexOf=function(s){return this.data.indexOf(s)};
	this.length=function(){return this.top;};
	this.clear=function(){this.top = 0;this.data.length=0;};
	this.all=function(a,l){l=[];for(a=0;a<this.top;a++)l.push(this.data[a]);return l;};
}

const files = {"roots":new Stack(cache_size),"datas":new Stack(cache_size)};//mpd 데이터
const mpds = {};
const events = {};

/* ======================================================================*/
const strByteLength = (s,b,i,c)=>{for(b=i=0;c=s.charCodeAt(i++);b+=c>>11?3:c>>7?2:1);return b};

/*
 * 파일을 로드하여 데이터 저장
 */
function get_file(host,roots,name) {
  var target = ["http:/",host,roots.join('/'),name].join('/');
	var cache = has_cache(target);
	if(cache != -1){
		console.log("load file : "+ name);
		return files.datas.get();
	}else console.log("new file : ",name);
	var data;
	try {
	  data = request('GET',target);
	} catch (e) {
		return false
	}
	var out = {
    'name':name,
    'length':strByteLength(data.getBody("utf-8")),
    'data':data.getBody("utf-8"),
    'target':target,
  };
	if(!cache)
		save_cache(out);
  return out;
}

async function save_cache(option){
	var index = files.roots.indexOf(option.target);
	if(index != -1){//데이터가 있을경우
		console.log("받은 데이터 존재설??????" + option.target);
		return index;
	}else {//없는경우
		files.roots.push(option.target);
		return files.datas.push(option);
	}
}

function has_cache(target){
	return files.roots.indexOf(target)
}

/* ======================================================================*/
function do_GET(response,pathname){
  const host = pathname.substring(1).split("/");// 타겟 호스
  if (!mpds.hasOwnProperty(host[0]))
    mpds[host[0]] = {};
  var target = ["http:/",host[0],host.slice(1,host.length-1),host[host.length-1]].join('/');
	var data = get_file(host[0],host.slice(1,host.length-1),host[host.length-1]);
	if (!data){
    response.writeHead(404,{'Content-Type':'text/html; charset=utf-8'});
    response.end("Not found");
		return;
	}
	if(/(\.mp4)$/i.test(host[host.length-1])){
		sendFile(response,data);
  }else if(/(\.m4s)$/i.test(host[host.length-1])){//파일 /(\.m4s|\.init)$/
		var option = mpd_num.exec(host[host.length-1]);
  	sendFile(response,data);
		if(Number(option[2]) == 1){// 1
			console.log("이벤트 등록 : "+option[0]);
			setImmediate(loadFile,host[0],host.slice(1,host.length-1),option[1],option[3]);
		}
  }else if(/(\.mpd)$/i.test(host[host.length-1])) {
		// 이미 해석한 데이터일경우 제외
		if (!mpds[host[0]].hasOwnProperty(host.slice(1,host.length-1).join("/")))
	    parser.parseString(data.data,function(err,result){
	      var mpd = [],option={};
	      var period = result.MPD.Period[0];// period
				option.name = host[host.length-1];
	      option.duration = period.$.duration;
	      option.length = period.AdaptationSet.length;// 트랙 길이
				option.cache = [0,0,0];
	      mpd.push(option);
	      console.log("===================================================");
	      for(var i=1;i<option.length;i++){
	        var arr = {};
	        var adaptationset = period.AdaptationSet[i];
	        var SegmentTemplate = adaptationset.SegmentTemplate[0];
	        arr.media = SegmentTemplate.$.media;//H_dash_track3_$Number$.m4s
	        arr.initialization = SegmentTemplate.$.initialization;//init.mp4 파일
	        arr.duration = SegmentTemplate.$.duration;//시간
	        arr.frameRate = adaptationset.Representation[0].$.frameRate;//
	        arr.bandwidth = adaptationset.Representation[0].$.bandwidth;//밴드위드
	        arr.id = adaptationset.Representation[0].$.id;
	        mpd.push(arr);
	      }
				console.log(host.slice(1,host.length-1).join("/"));
				console.log(mpd.length);
	      mpds[host[0]][host.slice(1,host.length-1).join("/")] = mpd;
	    });
    // 캐시 저장
    response.writeHead(206,{'Content-Type':'text/plain; charset=utf-8'});
    response.end(data.data);
  }else{
    response.writeHead(200,{'Content-Type':'text/plain; charset=utf-8'});
    response.end(JSON.stringify(mpds));
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

function loadFile(host,roots,name,index){// load to files
	console.log("++++++++++++++++++++++++++++++++++++++++");
	var root = roots.join("/");
	console.log(host,root,name,index,"미리 다운");
	var mpd = mpds[host][root][0];
	for(var i=1;i<=mpd.length;i++){

		get_file(host,roots,name+"_dash_track"+i+"_"+index+".m4s");
	}
	console.log(host,root,name,index,"미리 다운 완료");
}

/* ======================================================================*/

function sendFile(response, option){//데이터 전송부
  response.writeHead(200,{'Content-type':'application/octet-stream',"Content-Disposition":
    " attachment; filename="+option.name,"Content-Transfer-Encoding":" binary",
    "Content-Length":option.length});
  response.end(option.data);
}

http.createServer((request,response)=>{
  const urls = url.parse(request.url);
  //method / headers / httpVersion/ url
  do_GET(response,urls.pathname);
	if(urls.query && mpd_cache_qul.test(urls.query))setCache(urls.pathname,urls.query);
}).listen(8080,()=>{
  console.log("서버 on");
});

// 보조 스레드
setInterval(function() {
  console.log(Object.values(files.roots.data));
	// for(var h in mpds){
	// 	console.log(h);
	// 	for (var r in mpds[h]){
	// 		console.log("  ",r,JSON.stringify(mpds[h][r][0]));
	// 	}
	// 	console.log("======================================================================================");
	// }
	// console.log(Object.values(files.datas.data));
},5*1000);
