# Cached

## Getting Started with Development

I prefer using `pipenv` to do my work. Note that, [per recommendation](https://github.com/pypa/pipenv/issues/1911), we do not commit `Pipfile` or `Pipfile.lock`. Personally I would love to see `pipenv` support libraries as well as applications, but right now we are required to use setuptools as a library.

To get `pipenv` ready-to-use:
```sh
cd <project_repository>
# your library will bring the dependencies (via install_requires in setup.py)
pipenv install -e .
pipenv install --dev -e .[dev]
# start hacking
pipenv shell
```
