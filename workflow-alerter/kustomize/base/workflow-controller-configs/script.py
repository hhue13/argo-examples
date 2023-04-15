#!/usr/bin/env python3
import os
import json
import re
import sys
import urllib.request


class PDEvent():
    '''stores and sends a single event to pagerduty's event api'''
    def __init__(self, batch, status, pod):
        self.batch = batch
        self.status = status
        self.pod = pod

        self.event_action = 'trigger' if status != 'Succeeded' else 'resolve'

        self.environment = '{{ workflow.namespace }}'.split('-')[2]
        self.severity = 'error' if self.environment == 'prod' else 'info'

    def send(self):
        body = {
            'payload': {
                'summary':
                f'batch "{self.batch}" received status "{self.status}"\
                        on environment "{self.environment.upper()}"',
                'severity': self.severity,
                'source': self.pod,
                'group': '{{ workflow.namespace }}',
                'class': 'argo-workflow',
                'component': self.batch
            },
            'routing_key': 'R03DPCQDWH9P3VX3D5K3Y46ZAIHCB8WT',
            'dedup_key': f'{{ workflow.namespace }}/{self.batch}',
            'client': 'argo',
            'client_url':
                f'{self._get_client_url()}/workflows/{{ workflow.namespace}}/{{ workflow.name }}',
            'event_action': self.event_action
        }

        url = 'https://events.pagerduty.com/v2/enqueue'
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        jsondata = json.dumps(body)
        print(jsondata)
        jsondataasbytes = jsondata.encode('utf-8')
        req.add_header('Content-Length', len(jsondataasbytes))
        urllib.request.urlopen(req, jsondataasbytes)

    def _get_client_url(self):
        if self.environment == 'play':
            return 'https://argo-play.apps.fpx.azure.rabodev.com'

        return f'https://argo-{self.environment}.apps.fpx.azure.rabonet.com'


def print_script():
    '''if there is a script, display its contents'''
    for script in ('/argo/staging/script', 'script.py'):
        if os.path.exists(script):
            with open(script, 'r') as f:
                print(f.read())

    print('#############')


####### MAIN ###########
print_script()

workflow_failures=json.loads({{workflow.failures}}) \
        if {{workflow.failures}} != 'null' else []

print(workflow_failures)

events = []
if len(workflow_failures) < 1:
    batch='{{ workflow.labels.workflows.argoproj.io/cron-workflow }}'
    if re.match(r'{{.*}}', batch):
        batch='{{ workflow.labels.workflows.argoproj.io/workflow-template }}'

    status='{{ workflow.status }}'
    pod='{{ workflow.name }}'

    events.append(PDEvent(batch, status, pod))
else:
    for failure in workflow_failures:
        if failure['templateName'] == 'main': continue

        batch = failure['displayName']
        pod = failure['podName']
        status = failure['phase']

        events.append(PDEvent(batch, status, pod))

for event in events:
    event.send()
