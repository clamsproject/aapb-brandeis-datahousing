from flask.cli import FlaskGroup

import api


cli = FlaskGroup(api)


if __name__ == "__main__":
    cli()
