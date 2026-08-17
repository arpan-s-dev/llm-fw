# Deploy LLM-FW

Host: **Hugging Face Spaces**, Gradio on **ZeroGPU** (free personal accounts). Creating a Gradio Space on **CPU Basic** now requires [PRO](https://huggingface.co/pro). Static Spaces stay free; this demo is Gradio because it runs Python.

No GPU and no API key. The demo model is scripted on purpose.

## 1. Create a Hugging Face account

1. Sign up: https://huggingface.co/join
2. Enable **Spaces**: https://huggingface.co/new-space

## 2. Create the Space

On https://huggingface.co/new-space :

| Field | Value |
|-------|--------|
| Space name | `llm-fw` (or anything) |
| SDK | **Gradio** |
| Hardware | **ZeroGPU** (free). CPU Basic needs PRO. |
| Visibility | Public (for a showcase) |

Create the Space. Do **not** paste a huge README yet — you will push git.

## 3. Get a write token

1. https://huggingface.co/settings/tokens
2. **New token** → type **Write** → copy it.

## 4. Push this repo to the Space

In a terminal, from `LLM Firewall project` (the folder that contains `app.py` and `securing_ai_agents_with_information_flow_control/`):

```bash
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/llm-fw
git add -A
git status
git commit -m "Deploy LLM-FW demo"
git push space HEAD:main
```

Replace `YOUR_USERNAME` and `llm-fw` with your Space. Hugging Face will ask for:

- username: your HF username
- password: the **token**, not your account password

The Space builds in a few minutes. URL:

`https://huggingface.co/spaces/YOUR_USERNAME/llm-fw`

Open the **Logs** tab if the build fails.

## 5. What must be in the Space

These are enough. Do not upload PDFs, `.venv`, or `Project 1/`.

- `app.py` (repo root)
- `requirements.txt` (repo root)
- `README.md` (must keep the YAML block at the top)
- `securing_ai_agents_with_information_flow_control/app.py`
- `securing_ai_agents_with_information_flow_control/src/`
- `securing_ai_agents_with_information_flow_control/configs/base.yaml`

`.gitignore` already excludes papers, caches, virtualenvs, and `.env`.

## Alternate: upload only the inner folder

If you created an **empty** Gradio Space and want that folder to *be* the Space:

1. Copy everything inside `securing_ai_agents_with_information_flow_control/` (including its `README.md`, `app.py`, `src/`, `configs/`, `requirements.txt`).
2. Upload those files to the Space (Files tab → Contribute → Upload).

That inner `README.md` already has the required YAML.

## Local check before you push

```bash
pip install -r requirements.txt
python app.py
```

Browser: http://127.0.0.1:7860 (or the URL printed in the terminal).

Leave “Poison the web result” on, click **Run**. You should see EXFIL / DENY / ALLOW in the three columns.

## Optional: GitHub as well

```bash
git remote add origin https://github.com/YOUR_USERNAME/llm-fw.git
git push -u origin HEAD
```

Then on the Space: **Settings → Linked GitHub repository**. A push to GitHub will rebuild the Space.

## If the Space is blank or errors

- README YAML must start on line 1 (`---` then `sdk: gradio`).
- Hardware must be CPU, not a GPU you did not pay for.
- Logs: `ModuleNotFoundError: src` means `app.py` at the repo root is missing, or `src/` was not pushed.
- Do not set `share=True`. Spaces already give you a public URL.
