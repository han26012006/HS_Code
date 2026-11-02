"""Start the complete app: python serve.py; browser at http://127.0.0.1:8000."""
import argparse,os
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--open-browser',action='store_true');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=int(os.environ.get('PORT','8000')));a=p.parse_args()
    if a.open_browser:
        import threading,time,urllib.request,webbrowser
        def open_when_ready():
            url='http://127.0.0.1:'+str(a.port)
            for _ in range(40):
                try:
                    with urllib.request.urlopen(url+'/health',timeout=1):pass
                    webbrowser.open(url);return
                except Exception:time.sleep(.5)
        threading.Thread(target=open_when_ready,daemon=True).start()
    import uvicorn
    uvicorn.run('api:app',host=a.host,port=a.port,reload=True)
