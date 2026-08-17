# Reproduction Notes: Securing AI Agents with Information-Flow Control

> Every implementation choice: specified by the paper, taken from official code, or assumed.

---

## Paper

- **Title:** Securing AI Agents with Information-Flow Control
- **Authors:** Costa, Köpf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Béguelin
- **Year:** 2025
- **ArXiv:** https://arxiv.org/abs/2505.23643v2
- **Official code:** https://github.com/microsoft/fides (tutorial notebook, not the AgentDojo harness)

---

## What this implements

Fides: IFC-instrumented agent planners (Algorithms 2, 3, 5, 6, 7), P-T / P-F policies (§4.3), and a three-tool demonstration of the §1 indirect prompt injection.

---

## Verified against

- [x] Algorithm boxes 2, 3, 5, 6, 7 (§3.1, §4.2, Appendix C)
- [x] §4.1 lattice definitions (join of readers = intersection)
- [x] §4.3 P-T and P-F; Table 3 assignment for `send_email`
- [x] Official tutorial lattices (Tutorial.ipynb "Bounded lattices")
- [ ] Full AgentDojo 949-attack table (out of scope for this pass)
- [ ] Live gpt-4o / o3 numbers in Tables 1, 6–8

---

## Unspecified choices

| Component | Our Choice | Alternatives | Paper Quote | Section |
|-----------|-----------|--------------|-------------|---------|
| Max loop turns | 16 | 8, 32, unbounded | LOOP is recursive with no cap | — |
| Abort | `PolicyViolation` before `⟦f⟧` | Finish("blocked") | "abort" | Alg 5 |
| URL detector | `http://`, `https://`, `www.` | RFC 3986; MotW | "untrusted link" | App. D.1 |
| R(f)/W(f) syntax | explicit `reads`/`writes` on `ToolSpec` | infer from code | used in Alg 5, undeclared | §4.2 |
| Model M | scripted `InjectionFollowingModel` | Azure OpenAI (tutorial) | M uninterpreted | §3 |
| Enum vs enum in type lattice | equal iff same members, else join=string | bit-capacity | only `bool ⊑ enum ⊑ string` | §5.2 |
| `query_llm` decoding | stub returning `"false"` | Outlines / json_schema | cites [6, 2], no API | §5.2 |

---

## Known deviations

| Deviation | Paper says | We do | Reason |
|-----------|-----------|-------|--------|
| HIDE predicate | Alg 7: hide iff ℓ ≰ ℓσ (full product) | Default `hide_on: integrity` | Appendix D.1 evaluation: hide on integrity only |
| Policy on Query | Alg 5 checks only MakeCall | Same | Tutorial checks every action; paper algorithm wins |
| Three tools | AgentDojo toolset / Table 3 | `read_file`, `search_web`, `send_email` | Smallest viable architecture (user scope) |
| Variable names | `#tool-result-N.key#` (D.1) vs `#v1#` (examples) | D.1 structured names | Appendix is the identifier spec |

---

## Expected results

| Metric | Paper | This demo |
|--------|-------|-----------|
| ASR with policy checks | 0 on attacks that violate **P** (Finding 1, §8.1) | 0 on the §1 email exfil |
| ASR Basic, no policy | 156/949 gpt-4o (Table 1, parentheses) | 1/1 on the synthetic injection |
| Fides utility vs hiding | HIDE keeps context trusted so later P-T tools remain usable | Benign email to manager succeeds |

**Note:** Exact AgentDojo numbers need the official evaluation harness, the Table 3 tool set, and the listed model versions (§7.2).

---

## Debugging tips

1. **Attack still succeeds with P-T:** the injected text may not have tained the *tool label*. Alg 5 labels the model response with the join of the queried history. If `search_web` results never enter history, ℓ_f stays T.
2. **Fides still follows the injection:** HIDE did not fire (integrity of the page was T) or `inspect` expanded the variable. Check `planner.memory` and the tool-message content for `#...#`.
3. **P-F allows attacker recipient:** body label readers are the *universe* (public). Restricted files must keep their reader set through Alg 5 line 9 (`τ(x)` for `R(f)`).

---

## Scope decisions

### Implemented
- Lattices and labeled JSON trees — core contribution §4.1
- Planning loops Alg 2 and 5 — policy gate lives here
- Basic and Fides planners Alg 3, 6, 7
- P-T, P-F, P-F-or-P-T
- Three-tool world + scripted injection demo

### Intentionally excluded
- AgentDojo 97×35 evaluation — full-mode / later work
- Tool Filter baseline — comparison method (§7.2)
- Live Azure OpenAI client — tutorial only
- Formal proof of Proposition 1 — Appendix A, not code
- CaMeL dual-LLM interpreter — different paper
- Rust reverse proxy / DLP / sandbox — LLM-FW roadmap, not this paper

### Needed for full reproduction
- AgentDojo + Table 3 wrappers
- Model versions in §7.2
- Appendix D.1 system prompts (FIDES vs Variable Passing)
- Constrained-decoding backend for `query_llm`

---

## References

- Willison, Dual LLM pattern [32] — inspiration for `query_llm` / `inspect`
- AgentDojo [11] — evaluation suite
- microsoft/fides Tutorial.ipynb — lattice class names, `PolicyViolation`
