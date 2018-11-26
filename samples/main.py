from dci_runner.runner import Runner


r = Runner()

r.load_env_file('env.yml')
r.start(topic='OSP10')

r.run_playbook('set_a_fact.yml')
r.run_playbook('read_a_fact.yml')
