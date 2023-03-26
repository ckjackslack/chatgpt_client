# chatgpt client

This is small Poetry project containing just one simple script - *chatgpt.py*.

To run it you need Python **v3.8**.

Please make sure you've created *.env* file containg **OPENAI_API_KEY** key-value pair.

To obtain it, you must login to your OpenAI account and visit [OpenAI Api Keys](https://platform.openai.com/account/api-keys), where you can generate api token to be able to use the script.

## Setup

if you want to use Poetry

```bash
$ poetry install
$ poetry shell
```

or without Poetry (globally)

```bash
python3 -m pip install -r requirements.txt
```

## Usage

At first interaction *prompts.db* file will be created, which will preserve your prompts and responses for later.

Available CLI subcommands:

1) List all prompts from database

```bash
$ python3 chatgpt.py
```

or

```bash
$ python3 chatgpt.py --action="show"
```

2) Show full response for given database entry id

```bash
$ python3 chatgpt --id=1
```

3) Search for all code in your current prompt database (either valid Python code in response column, or snippets found between Markdown backticks.

```bash
$ python3 chatgpt.py --action="search"
```

4) Send your query to chatgpt to get back the response (it will be printed to stdout and inserted into database for later retrieval)

```bash
$ python3 chatgpt --action="ask" --query="How much is the fish?"
```

5) Clear the database (to start over again)

```bash
$ python3 chatgpt.py --action="clear"
```
