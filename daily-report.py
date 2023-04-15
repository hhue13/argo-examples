#!/usr/bin/env python3

from helpers import *


def main():
    set_logging('info')

    yesterday = localtime(datetime.today() - timedelta(days=1))
    last_batches_start = yesterday.replace(hour=21, minute=0)

    logging.info(f'retrieving workflows, starting from \
        {last_batches_start.strftime("%Y-%m-%d %H:%M")}')

    wf_objs = []
    for wf in get_argo_workflow_list():
        wf_obj = Workflow(wf)
        if wf_obj.startdt >= last_batches_start:
            wf_objs.append(wf_obj)

    wf_objs.sort(key=lambda x: x.startdt)

    logging.info('generating html output')
    now_str = localtime(datetime.now()).strftime('%Y-%m-%d %H:%M')
    start_str = last_batches_start.strftime('%Y-%m-%d %H:%M')
    title_str = f'{now_str} - Daily Workflow Report for environment: {get_environment().upper()}'

    wf_html_output = (
        f'<p>Reporting current status of Argo Workflows run<br />'
        f'From: <b>{start_str}</b><br />'
        f'Till: <b>{now_str}</b><br /></p>'
    )
    logging.info("appending regular workflows to output")
    wf_html_output += get_wf_html_outputstring(wf_objs)
    logging.info("appending missing workflows to output")
    wf_html_output += get_missing_workflows(wf_objs)

    logging.info('sending msteams output')
    send_msteams(html_body=wf_html_output, title=title_str)


if __name__ == '__main__':
    main()
