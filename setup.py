import setuptools

VERSION = '0.0.0'

setup_params = dict(
    name='cached',
    version=VERSION,
    author='Kenneth VanderLinde',
    author_email='kwvanderlinde@gmail.com',
    url='https://github.com/kwvanderlinde/cached',
    keywords='requests cache',
    packages=setuptools.find_packages(),
    package_data={'': ['LICENSE.txt']},
    package_dir={'cached': 'cached'},
    include_package_data=True,
    description='Memory-efficient caching for the requests library and Python 3',
    long_description=open('README.md').read(),
    install_requires=['requests~=2.18.4', 'dataclasses~=0.6;python_version<"3.7"'],
    extras_require={
        'dev': {
            'mockito': '~=1.1.1',
            'pytest': '~=5.1.2',
            'pytest-cov': '~=2.7.1',
            'ddt': '~=1.2',
        }
    },
    entry_points={},
    python_requires='>=3.4',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha'
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',

        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
    ],
)


if __name__ == '__main__':
    setuptools.setup(**setup_params)
