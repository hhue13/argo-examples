#!/usr/bin/env python3

import os
import sys
import logging
import pymsteams
import requests
import smtplib
import urllib3

from datetime import datetime, timedelta
from dateutil import tz
from email.message import EmailMessage

urllib3.disable_warnings()

class Workflow(object):
    def __init__(self, wf):
        self.name = wf.get('metadata').get('name')
        self.template = 'empty'
        self.phase = wf.get('status').get('phase')
        self.progress = wf.get('status').get('progress')

        if 'workflowTemplateRef' in wf['spec']:
            self.template = wf.get('spec').get('workflowTemplateRef').get('name')
        start = wf.get('status').get('startedAt')
        finish = wf.get('status').get('finishedAt')

        self.startdt = self._get_dateobj(start)
        self.finishdt = self._get_dateobj(finish)

        self.duration = self._get_duration()

        self.report_url = self._get_report_url(wf)

    def _get_duration(self):
        duration = 0
        if self.finishdt:
            duration = int((self.finishdt - self.startdt).seconds / 60)

        return duration

    def _get_dateobj(self, date: str) -> datetime:
        """return input date string to a datetime object or return a time in future if its not ready"""
        if date:
            return datetime.strptime(date, '%Y-%m-%dT%H:%M:%S%z').astimezone(tz.gettz('UTC'))
        else:
            return datetime.strptime('31-12 2050', '%d-%m %Y').astimezone(tz.gettz('Europe/Amsterdam'))

    def _format_dateobj(self, dateobj: datetime) -> str:
        return localtime(dateobj).strftime('%m-%d %H:%M')

    def __str__(self):
        return f'{self.template:50}\t{self._format_dateobj(self.startdt)}\t{self._format_dateobj(self.finishdt)}\t{self.duration:8}\t{self.phase:12}\t{self.progress}'

    def _get_report_url(self, wf):
        """check if this workflow is triggered by a sensor or cronjob or manual and return the appropriate report url"""
        workflow_labels = wf.get('metadata').get('labels')

        report_labels = (
            'events.argoproj.io/sensor',
            'workflows.argoproj.io/cron-workflow',
            'workflows.argoproj.io/workflow-template'
        )
        for label in report_labels:
            if label in workflow_labels.keys():
                label_value = workflow_labels.get(label)
                return generate_report_url(label, label_value)


def generate_report_url(
        label: str = 'workflows.argoproj.io/workflow-template',
        label_value: str = '') -> str:
    '''generate a url targetting the historic reports of this workflowtemplate

    >>> generate_report_url(label_value='my-workflowtemplate')
    'https://argo-play.apps.fpx.azure.rabodev.com/reports?labels=workflows.argoproj.io/workflow-template=my-workflowtemplate&archivedWorkflows=true'
    '''
    return f'{get_argo_server_url()}/reports?labels={label}={label_value}&archivedWorkflows=true'


def set_logging(loglevel):
    '''set default options for logging

    >>> set_logging('debug')
    '''
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    logging.basicConfig(
        stream=sys.stdout,
        level=numeric_level,
        datefmt='%Y-%m-%d %H:%M:%S',
        format='%(asctime)s - %(levelname)s - %(message)s')


def localtime(date_obj: datetime) -> datetime:
    '''convert a utc time to localtime'''
    return date_obj.astimezone(tz.gettz('Europe/Amsterdam'))


def get_environment():
    '''determine the environment based on the namespace where this is run from

    >>> os.environ['ARGO_NAMESPACE'] = 'development'
    >>> get_environment()
    'development'
    '''
    namespace = os.environ['ARGO_NAMESPACE']
    environment = namespace.split('-')[2]

    return environment


def get_argo_server_url():
    argo_server = os.environ['ARGO_SERVER']

    return argo_server[get_environment()]


def send_email(body='', html_body='', to_addr='', subject='Daily Report'):
    """https://docs.python.org/3/library/email.examples.html#email-examples"""
    from_addr = 'no-reply@acme.com'

    msg = EmailMessage()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject

    msg.add_header('Content-Type', 'text/html')
    msg.set_content(body)
    msg.add_alternative(f"""\
        <html>
            <head></head>
            <body>
                {html_body}
            </body>
        </html>""", subtype='html')

    with smtplib.SMTP('email_server.svc.cluster.local', 25000) as smtp:
        smtp.send_message(msg)

    logging.info(f'email sent to {to_addr}')


def send_msteams(html_body: str = '', title: str = 'Daily Batch Report'):
    '''https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-format?tabs=adaptive-md%2Cconnector-html#format-cards-with-html'''
    MS_TEAMS_WEBHOOK = os.environ['MS_TEAMS_WEBHOOK']
    msg = pymsteams.connectorcard(MS_TEAMS_WEBHOOK)
    msg.title(title)
    msg.text(html_body)
    msg.send()


def get_wf_html_outputstring(wf_list: list[Workflow]) -> str:
    """return a html string of the workflow output"""
    result = '<table><tr>'
    for header in ('Workflow', 'Started', 'Finished', 'Duration (min)', 'Phase', 'Progress', 'History'):
        result += f'<th>{header}</th>'
    result += '</tr>'

    rowcolor = {
        'Succeeded': '#98FB98',
        'Failed': '#FA8072',
        'Running': '#40E0D0'
    }

    namespace = os.environ['ARGO_NAMESPACE']
    for wf in wf_list:
        result += f'''
            <tr style="background-color: {rowcolor[wf.phase]}">
            <td>{wf.template.split('-workflowtemplate')[0]}</td>
            <td>{wf._format_dateobj(wf.startdt)}</td>
            <td>{wf._format_dateobj(wf.finishdt)}</td>
            <td>{wf.duration}</td>
            <td><a href="{get_argo_server_url()}/workflows/{namespace}/{wf.name}">{wf.phase}</a></td>
            <td>{wf.progress}</td>
            <td><a href="{wf.report_url}">history</a></td>
            </tr>
            '''

    return result + '</table>'


def get_argo_workflow_list():
    logging.debug("token_path uses the token which is mounted in Kubernetes")
    token_path = '/var/run/secrets/kubernetes.io/serviceaccount/token'
    if os.path.exists(token_path):
        with open(token_path, encoding='utf-8') as f:
            access_token = 'Bearer ' + f.read().rstrip()
    else:
        access_token = os.environ['ARGO_TOKEN']

    namespace = os.environ['ARGO_NAMESPACE']

    logging.info(f'requesting workflowdata from {get_argo_server_url()}')
    response = requests.get(
        f'{get_argo_server_url()}/api/v1/workflows/{namespace}',
        headers={
            "Authorization": access_token
        },
        verify=False)

    response.raise_for_status()

    return response.json()['items']


def get_missing_workflows(wf_list: list[Workflow], templates: list[dict] = None) -> str:
    '''return a list of failed workflows in html format'''
    env = get_environment()
    mandatory_templates = templates if templates else [
        {
            'sensor': f'{env}-event-sensor',
            'template': f'{env}-complete-workflowtemplate'
        },
    ]

    missing_templates = (
        '<p><table><caption>The following templates were not found</caption>'
        '<tr><th>Workflow</th><th>Automatic History</th><th>Manual History</th></tr>'
    )

    workflowtemplates = set(map(lambda x: x.template, wf_list))
    for tmpl in mandatory_templates:
        if tmpl['template'] not in workflowtemplates:
            missing_templates += (
                f'<tr style="background-color: #FA8072"><td>{tmpl["template"].split("-workflowtemplate")[0]}</td>'
                f'<td><a href="{generate_report_url(label="events.argoproj.io/sensor",label_value=tmpl["sensor"])}">automatic</a></td>'
                f'<td><a href="{generate_report_url(label_value=tmpl["template"])}">manual</a></td></tr>'
            )

    return missing_templates + '</table></p>'
