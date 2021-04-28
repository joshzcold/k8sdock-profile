#!/usr/bin/env python3
import sys
import threading
from argparse import ArgumentParser
from time import sleep
import subprocess
import traceback
import signal
import re
from os import system, name, environ, path
import json
con_dict = {}

def signal_handler(sig, frame):
    try:
        for pod in con_dict:
            con_dict[pod]['cpu'] = 0
            con_dict[pod]['mem'] = 0
            for container in con_dict[pod]['containers']:
                con_dict[pod]['cpu'] += con_dict[pod]['containers'][container]['cpu']
                con_dict[pod]['mem'] += con_dict[pod]['containers'][container]['mem']
        file = "kd-profile.json"
        if args.file:
            file = args.file
        print('\n writing to file ==> ', file)
        content = ""
        content = json.dumps(con_dict, indent = 4, sort_keys=True)
        print(content)
        with open(file, 'w') as outfile:
            json.dump(con_dict, outfile, indent=4, sort_keys=True)
    except:
        traceback.print_exc()
        sys.exit(1)
    sys.exit(0)

def parse_int(string):
    return int(re.sub(r'[^\d-]+', '', string))

def profile_k8s():
    if args.label_selectors:
        query = f" -l {args.label_selectors}"
    else:
        query = ""
    command = f"kubectl top pods --no-headers --containers -n {args.namespace or 'default'}{query}"
    if args.search:
        command += f"| grep {args.search}"
    print(command)
    while True:
        normal = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        stats = normal.communicate()[0].decode("utf-8")
        pod_list = stats.split("\n")
        for pod in pod_list:
            if pod:  # pod is not empty
                i = pod.split()
                if args.namespace:
                    namespace, pod, container, cpu, mem = args.namespace,i[0],i[1],parse_int(i[2]),parse_int(i[3])
                else:
                    namespace, pod, container, cpu, mem = i[0],i[1],i[2],parse_int(i[3]),parse_int(i[4])
                if pod not in con_dict:
                    con_dict[pod] = {
                        "namespace": namespace,
                        "containers":{}
                    }
                if container not in con_dict[pod]['containers']:
                    con_dict[pod]['containers'][container] = {
                        "cpu": cpu,
                        "mem": mem
                    }
                else:
                    if con_dict[pod]['containers'][container]["cpu"] < cpu:
                        con_dict[pod]['containers'][container]["cpu"] = cpu
                    if con_dict[pod]['containers'][container]["mem"] < mem:
                        con_dict[pod]['containers'][container]["mem"] = mem
        if not args.quiet:
            print(json.dumps(con_dict, indent=4))

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-n", "--namespace", help="choose k8s namespace")
    parser.add_argument("-f", "--file", help="choose file to output to")
    parser.add_argument("-s", "--search", help="fuzzy match search term using grep")
    parser.add_argument("-l", "--label-selectors", help="k8s selector query ex: key1=value1,key2=value2")
    parser.add_argument("-t", "--timeout", help="time in seconds to run the script and exit. Default is to run forever.")
    parser.add_argument("-q", "--quiet", help="quiet mode", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    print("Press Ctrl + C to stop and write results to file")
    print("------------------------------------------------")
    # TODO We need to fix the OS path is file
    if not environ.get("KUBECONFIG") and not path.isfile("~/.kube/config"):
        raise Exception("KUBECONFIG env var and ~/.kube/config not set")
    if args.timeout:
        p = threading.Thread(target=profile_k8s, args=())
        p.daemon = True
        p.start()
        sleep(int(args.timeout))
        signal_handler("","")
    else:
        profile_k8s()
