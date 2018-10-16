
.PHONY: migrate kill fmt


# inside travis the virtualenv is already set up, so just mock these commands
ifeq ($(TRAVIS),true)
activate = true
venv:
	mkdir -p venv
else
activate = . venv/bin/activate
venv:
	virtualenv --quiet --python python3 --no-site-packages $@
	${activate} && pip install --quiet -r requirements.txt
endif

static: venv
	${activate} && ./manage.py collectstatic --no-input

update_slacknames: venv
	${activate} && ./manage.py shell -c "import crossbot.models as m; m.CBUser.update_slacknames()"

fmt: venv
	${activate} && yapf -pri crossbot/ *.py

check_fmt: venv
	${activate} && yapf -pr --diff crossbot/ *.py

migrate: venv
	${activate} && ./manage.py migrate

test: venv
	${activate} && ./manage.py test

kill:
	kill `cat /tmp/crossbot.pid` || true

run: kill venv static migrate
	${activate} && gunicorn --daemon --workers 4 --pid /tmp/crossbot.pid --bind "unix:/tmp/crossbot.sock" "wsgi:application"