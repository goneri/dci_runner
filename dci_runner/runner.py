# pylint: skip-file
import io
import os
import os.path
import tempfile
import yaml

import ansible_runner
import dci.client

# job_info_file = '/var/lib/dci-openstack-agent/job_info.yaml'
# settings_file = '/etc/dci-openstack-agent/settings.yml'
# share_dir = '/usr/share/dci-openstack-agent'
# work_dir = '/home/goneri/git_repos/dci-runner/var'



class DCIRunnerPlaybookFailure(Exception):
    pass


class Runner:

    def __init__(self):
        self.extravars = {}
        self._c = dci.client.DCIClient()
        self.has_failed = None


    def load_env_file(self, path):
        with open(path, 'r') as fd:
            self.add_extravars(yaml.load(fd))

    def add_extravars(self, data):
        for k, v in data.items():
            self.extravars[k] = v


    def start(self, topic):
        c = self._c
        topic = c.topics.first(where='name:%s' % topic)
        self._job = c.jobs.schedule(topic=topic)
        self._jobstate = c.jobstates.add(
            comment='new',
            job=self._job,
            status='new')
        print(self._job)
        self.add_extravars({
            'job_id': self._job.id
        })


    def add_message(self, name, message):
        c = self._c
        c.files.add(
        data=io.StringIO(message),
        jobstate=self._jobstate,
        name=name)

    def run_tasklist(self, tasklist_file):
        with open(tasklist_file, 'r') as fd:
            tasklist = yaml.load(fd)
            print(tasklist)
            content = [{
                'hosts': 'localhost',
                'tasks': tasklist
            }]
            with tempfile.NamedTemporaryFile(mode='w+', delete=True) as tmp_f:
                tmp_f.write(yaml.dump(content))
                tmp_f.seek(0)
                self._run(tmp_f.name)


    def run_playbook(self, playbook):
        if os.path.isabs(playbook):
            path = playbook
        else:
            path = os.path.join(os.getcwd(), playbook)
        print('Calling %s!' % path)
        self._run(path)

    def _run(self, playbook):
        c = self._c
        job = self._job
        def event_handler(event):
            if event['event'] == 'playbook_on_task_start':
                return
            has_failed = bool(len(event['event_data'].get('failures', {})))
            output = event.get('stdout', '')
            if output:
                output += '\n'
            if has_failed:
                self._jobstate = c.jobstates.add(
                    comment='failure',
                    job=job,
                    status='failure')
                self.add_message('failure', event['stdout'])
                self.has_failed = True
            elif event['event_data'].get('task_action'):
                output += '%s - %s - %s' % (
                    event['event_data'].get('task_action'),
                    event['event_data']['task_args'],
                    event['event_data'].get('task_path'))
                self.add_message(event['event_data']['task'], output)

                if event['event_data']['task_action'] == 'set_fact':
                    data = event['event_data']['res']['ansible_facts']
                    self.add_extravars(data)

            elif event['event_data'].get('task'):
                output += '%s - %s - %s' % (
                    event['event_data'].get('task'),
                    event['event_data']['task_args'],
                    event['event_data'].get('task_path'))
                self.add_message(event['event_data']['task'], output)
            else:
                print("  > NON TASK: %s" % event['event_data'])
        envvars = {k: os.environ[k] for k in os.environ if k.startswith('DCI_')}
        result = ansible_runner.run(
            playbook=playbook,
            inventory='localhost ansible_user=root ansible_connection=local',
            envvars=envvars,
            extravars=self.extravars,
            private_data_dir=os.getcwd(),
            event_handler=event_handler)
        print('result: %s' % result)
        print('events: %s' % result.events)
        for e in result.events:
            print(e)
        print('stats: %s' % result.stats)
        print('stdout: %s' % result.stdout)
        #if not result.stats or result.stats['failures']:
        if self.has_failed:
            raise DCIRunnerPlaybookFailure(result)
        return result
