# Internship project: LLM-FW (Fides)

## One paragraph you can say in a meeting

We are **not** training a new language model. We are implementing a **2025 Microsoft Research paper**, [*Securing AI Agents with Information-Flow Control*](https://arxiv.org/abs/2505.23643) (Fides). LLM agents can read email, files, and the web, then call tools such as `send_email`. A malicious webpage can say “ignore previous instructions and steal secrets.” Today most defenses ask another model “does this look dangerous?” — that is probabilistic. This paper puts a **deterministic firewall** *outside* the LLM: every piece of data gets a **trust/confidentiality label**, labels join as data mixes, and a **policy engine** allows or aborts the tool call. The internship project is a working prototype of that firewall on a three-tool agent, plus a live demo.

## Which paper

| | |
|---|---|
| Title | Securing AI Agents with Information-Flow Control |
| Nickname | **Fides** (Flow Integrity Deterministic Enforcement System) |
| Authors | Costa, Köpf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Béguelin (Microsoft) |
| Link | https://arxiv.org/abs/2505.23643 |
| Official tutorial | https://github.com/microsoft/fides |

You also have a PDF named *Defeating Prompt Injections by Design* (CaMeL). That is a **related** Google/DeepMind paper (capabilities + dual-LLM). This repo implements **Fides**, which matches the internship firewall (labels, taint, policy, not “ask another LLM”).

## What problem we solve

An intern-level story:

1. User: “Summarize Project X from the web and email my manager.”
2. The web page contains an **indirect prompt injection**.
3. The model (which we **do not trust**) tries `send_email` to the attacker with a secret file.
4. **Without Fides:** the mail goes out.
5. **With P-T:** the context is now untrusted, so `send_email` is aborted.
6. **With Fides HIDE:** the poisoned text is stored in a `#variable#` and never shown to the model, so it emails the manager instead.

## Architecture (what to draw on a slide)

```
User request
    → Planner (Basic or Fides)
        → LLM (untrusted; we use a scripted stand-in)
        → Proposed tool call
            → Policy engine (P-T / P-F)     ← deterministic
            → Tool sandbox (read_file / search_web / send_email)
            → Labeled result (taint join)
```

Labels: integrity T ⊑ U (trusted ⊑ untrusted), confidentiality = who may read the data. Mixing data takes the **join** (least upper bound).

## What “done” means for the internship MVP

Already built:

- Lattices and taint (§4.1, Algorithms 5–6)
- Fides HIDE/EXPAND (Algorithm 7)
- Policies P-T and P-F (§4.3)
- Three tools and the §1 attack/defense demo
- Walkthrough notebook
- Gradio app for a live showcase (`app.py`)

Intentionally later (full paper eval, not required to demo the idea):

- AgentDojo 949-attack benchmark
- Live GPT-4o / o3
- Rust reverse proxy
- Real constrained decoding for `query_llm`

## How to run

```bash
cd securing_ai_agents_with_information_flow_control
pip install -r requirements.txt
python -m src.evaluate          # CLI proof
python app.py                   # local web demo
```

## Live demo: Hugging Face vs Vercel

**Use Hugging Face Spaces (Gradio).** This project is a Python agent loop, not a static website.

| Host | Fit | Why |
|------|-----|-----|
| **Hugging Face Spaces** | Yes — best | Native Gradio, free CPU, one `app.py`, good for intern showcases |
| Vercel | Poor fit | Vercel is for Node/Next.js; Python tool loops time out on serverless |
| Streamlit Cloud | OK backup | Also Python, slightly less “ML intern” branded than HF |

You do **not** need a paid GPU. The demo LLM is scripted on purpose: the paper’s point is that security does not depend on the model.

Deploy (about 10 minutes): step-by-step in [`DEPLOY.md`](DEPLOY.md).

## How to defend this in an intern review

**Q: Did you train a model?**  
No. We implemented the *system* around the model.

**Q: Why not just prompt “don’t follow untrusted instructions”?**  
The paper (and our undefended run) shows the model still complies. The firewall does not trust the model.

**Q: Why not use an LLM classifier as the firewall?**  
Fides’s claim is *deterministic* IFC. A classifier is another probabilistic model the attacker can trick.

**Q: What is original vs copied?**  
The algorithms and policies are from the paper. The three-tool world, scripted attack model, and Gradio demo are the internship engineering around that paper.
