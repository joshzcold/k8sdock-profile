# Objective
Sometimes when deploying k8s pods, resource management is of more importance

In pod definitions you can create `resource requests` to determine how much an
individual container should be allowed to use within the pod. 

```yaml
resources:
  requests:
    cpu: 500m
    memory: 500Mi
```

Result:

cpu => throttled to mhz and or % of a single core on k8s node

ram => if exceeding limit then kill/restart container

If you are deploying an application you yourself did not create then it can be tricky 
to determine how much cpu and ram to allocate

This script will give you an accurate stats on either docker containers or k8s pods 
over the course of their workload so you can make better decisions on your resource requests

This script will output the max utilized CPU and RAM in mb/mhz

If you are deploying for one of these scenarios then this script can be helpful:

- On Prem K8S cluster with limited resources
- Deploying many testing pods 
- unsure how much resources to allocate an individual container
- get stats on an application during any workload

> Personally in my setup I deploy many testing applications in parallel. If I over utilize the cluster then k8s will have pods wait their turn for resources. This is essential because my application consumes about 6CPU 10 GB RAM per each pod.


Some added bonuses to resource requests in k8s pods:

- k8s only schedules pods if requested resources are available 
- k8s pods don't get a chance to kill Nodes on the cluster

# Usage

```sh
usage: k8s-dock-profile.py [-h] [-d] [-k] [-n NAMESPACE] [-f FILE]

optional arguments:
  -h, --help            show this help message and exit
  -d, --docker          profile docker containers
  -k, --kubernetes      profile k8s pods containers
  -n NAMESPACE, --namespace NAMESPACE
                        choose k8s namespace
  -f FILE, --file FILE  choose file to output to
```

To start profiling on k8s pods. Note: this just gathers from `kubectl top` 

```sh
python3 ./k8s-dock-profile.py -k
```

Profile on k8s pods in namespace

```sh
python3 ./k8s-dock-profile.py -k -n my-namespace
```

Docker containers on local machine
```sh
python3 ./k8s-dock-profile.py -d
```

By default results output to `k8s-dock.profile`

To output to a different file

```sh
python3 ./k8s-dock-profile.py -d -f my-file.txt
```

To Stop the Application send a SigTERM `Ctrl + C`

