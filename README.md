# CTF Scenario-DSL
This app generates a CTF scenario based on the input specified declaratively using a domain specific language that is designed and created as part of a Master thesis at NTNU Gjøvik.

### Requirements
* oyaml
* python-heatclient
* python-openstackclient


### Setup

```
git clone https://github.com/dunf/master-thesis.git
cd master-thesis
virtualenv3 py3-env
source py3-env/bin/activate
pip3 install oyaml
pip3 install python-heatclient
pip3 install python-openstackclient
```
### Usage
```
python3 main.py examples/example-attack-defense-minimal.yaml --debug
python3 py3-env/bin/openstack stack create -t templates/debug.yaml teststack
```

