import os
from socket import timeout 
import sys 
import time 
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List

def run_cmd_sync(cmd:List[str])->bool:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,env=os.environ)
    while p.poll() is None:
        line = p.stdout.readline()
        line = line.strip()
        if line:
            try:
                print("\t",line.decode(encoding='utf-8')) 
            except Exception as e:
                try:
                    print("\t",line.decode(encoding='gbk')) 
                except Exception as e:
                    print("\t",line) 
    return p.returncode == 0

class AutoRestartThreadContainer(threading.Thread):
    def __init__(self,entry:Callable,*args,exit_on_program_terminate:bool=True,auto_restart:bool=False,only_restart_on_err:bool=False,reduce_restart_freq:bool=True,reduce_lambda:Callable[[int],int]=lambda x:2**x):
        threading.Thread.__init__(self)
        if exit_on_program_terminate:
            self.setDaemon(True)
        else:
            self.setDaemon(False)
        self.auto_restart = auto_restart
        self.only_restart_on_err=only_restart_on_err
        self.reduce_restart_freq=reduce_restart_freq
        self.reduce_lambda=reduce_lambda
        self.last_crash_counter=0
        self.entry=entry
        self.args=args
        
    def run(self):
        while True:
            err=None
            try:
                self.entry(*self.args)
            except Exception as e:
                err=e
            if not self.auto_restart or (self.only_restart_on_err and err==None):
                if err!=None:
                    raise err
                # print("Thread Exit")
                return
            else:
                delay_time=0
                self.last_crash_counter+=1
                if err!=None and self.reduce_restart_freq:
                    delay_time=self.reduce_lambda(self.last_crash_counter)
                print(f"Thread terminated, "+f"because of error {err}, " if err is not None else ""+f"and will restart on {delay_time}s")
                if delay_time>0:time.sleep(delay_time)

def execute_func_in_thread_with_auto_restart(func:Callable,*args,exit_on_program_terminate:bool=True,
                                             auto_restart:bool=False,only_restart_on_err:bool=True,
                                             reduce_restart_freq:bool=True,reduce_lambda:Callable[[int],int]=lambda x:2**x)->AutoRestartThreadContainer:
    container=AutoRestartThreadContainer(func,*args,exit_on_program_terminate=exit_on_program_terminate,
                                         auto_restart=auto_restart,only_restart_on_err=only_restart_on_err,reduce_restart_freq=reduce_restart_freq,reduce_lambda=reduce_lambda)
    container.start()
    return container

def create_value_with_hook(value:any,on_get:Callable[[any],any]=lambda x:x,on_set:Callable[[any],any]=lambda o,n:n):
    class DummyValueClass(object):
        def __init__(self,value,on_get,on_set) -> None:
            self.value=value
            self.on_get=on_get
            self.on_set=on_set
        
        @property
        def _value(self):
            return self.on_get(self.value)
        
        @_value.setter
        def set_value(self,x):
            self.value=self.on_set(self.value,x)
    return DummyValueClass(value=value,on_get=on_get,on_set=on_set).set_value


def crash(reason:str):
    raise Exception(reason)



@dataclass
class StartUpArgs:
    named_args:Dict[str,str]=None
    unnamed_arg:List[str]=None 
    cwd:str=None
    script_name:str=None
    omega_lib_path:str=None
    python_exec:str=None
    
def _collect_startup_args()->StartUpArgs:
    this_file_dir=__file__
    lib_path=os.path.dirname(this_file_dir)
    cwd=os.getcwd()
    args=sys.argv
    script_name=args[0]
    options=args[1:]
    python_exec=sys.executable
    
    # ????????????????????????python?????????args???????????????
    # ??????????????????????????????????????????
    
    named_args_dict={}
    unnamed_args=[]
    next_arg_fn=None
    for o in options:
        if o.startswith(("-","--")):
            named_args_dict[o]=None
            _arg_name=o
            def put_arg_value(o):
                named_args_dict[_arg_name]=o
            next_arg_fn=put_arg_value
            continue
        if next_arg_fn is not None:
            next_arg_fn(o)
            continue
        unnamed_args.append(o)
        
    return StartUpArgs(named_args=named_args_dict,unnamed_arg=unnamed_args,cwd=cwd,script_name=script_name,omega_lib_path=lib_path,python_exec=python_exec)

@dataclass
class OmegaEnvArgs:
    cwd:str=None
    script_name:str=None
    omega_lib_path:str=None
    ws_server_addr:str=None
    python_exec:str=None
    lib_3rd_install_path:str=None
    start_up_args:StartUpArgs=None
    is_running:bool=False
    # ws:any=None
    
def _init_omega_env_args()->OmegaEnvArgs:
    '''
        1. ??????omega?????????ws??????????????????????????? -s ????????????????????? --server ?????????????????????????????????????????? ws://localhost:24011/omega_side
        2. ??????????????????????????????????????????????????????????????????????????????????????????????????? docker???????????????????????????????????????????????????
    '''
    start_up_args=_collect_startup_args()
    omega_env_args=OmegaEnvArgs(cwd=start_up_args.cwd,
                                script_name=start_up_args.script_name,
                                omega_lib_path=start_up_args.omega_lib_path,
                                python_exec=start_up_args.python_exec,
                                start_up_args=start_up_args)
    if "--server" in start_up_args.named_args.keys():
        omega_env_args.ws_server_addr=start_up_args.named_args["--server"]
    elif "-s" in start_up_args.named_args.keys():
        omega_env_args.ws_server_addr=start_up_args.named_args["-s"]
    else:
        omega_env_args.ws_server_addr="ws://localhost:24011/omega_side"
    omega_env_args.lib_3rd_install_path=os.path.join(os.path.abspath(os.path.join(omega_env_args.omega_lib_path,"..")),"python3_3rd_libs")
    os.makedirs(omega_env_args.lib_3rd_install_path,exist_ok=True)
    sys.path.append(omega_env_args.lib_3rd_install_path) 
    return omega_env_args

# ?????????????????????
omega_args=_init_omega_env_args()
start_up_args=omega_args.start_up_args

def change_server_addr_before_start(addr:str):
    omega_args.ws_server_addr=addr
    return addr

def install_lib(lib_name:str,lib_install_name:str=None,mirror_site:str="https://mirrors.bfsu.edu.cn/pypi/web/simple",python_exec:str=None,install_path=None)->bool:
    '''
        ??????????????????,lib_name ??? import????????????,lib_install_name ??? pip install ????????????
        ????????????,lib_name ??? lib_install_name ????????????
        ?????????????????????
        import websocket 
        ?????? websocket ????????????????????????????????????,???????????????pip??????????????????websocket-client???????????????
        install_lib(lib_name="websocket",lib_install_name="websocket-client")
    '''
    import importlib
    try:
        importlib.import_module(lib_name)
        return True
    except Exception as e:
        # print(e)
        pass 
    print(f"???????????????: {lib_name}")
    if python_exec is None:
        python_exec=omega_args.python_exec
    if install_path is None:
        install_path=omega_args.lib_3rd_install_path
    if lib_install_name is None:
        lib_install_name=lib_name
    cmd=[python_exec,"-m","pip","install","-i",mirror_site,f"--target={install_path}",lib_install_name]
    if run_cmd_sync(cmd):
        return True
    else:
        raise Exception(f"??? {lib_name} ????????????")

# ?????????omega????????????
install_lib("easydict")
install_lib(lib_name="websocket",lib_install_name="websocket-client")
install_lib('dataclasses_json')
install_lib('requests')

import requests
def download_file(url:str,local_filename:str=None,chunk_size:int=1024,timeout:int=0):
    if local_filename is None:
        local_filename = url.split('/')[-1]
    r = requests.get(url, stream=True,timeout=timeout)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=chunk_size): 
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return local_filename
