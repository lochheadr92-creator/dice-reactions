# Foundation Canon Source Map — v0.1

**Branch:** `reimplementation/foundation-systems-v01`  
**Base:** `4dadb3feb3737b28a4e5fbb1ef71aa0d56b365a5`  
**Classification:** NEW FOUNDATION IMPLEMENTATION v0.1 — DOCUMENTED DIVERGENCE FROM CANON (runtime integration partial; provisional paths retained)

## Canonical source path

| Document | Path |
|----------|------|
| Source of Truth v1.2 | `C:/Users/RJLoc/OneDrive/Desktop/Source of Truth/Source of Truth/Source_of_Truth_v1.2.md` |
| Appendix A / Constants Registry | Same file, lines 20817–20930 |
| Chapter 25 Actor Resolution | Same file, lines 18252–18588 |
| Chapter 26 Gravity Governance | Same file, lines 18592–18801 |
| Chapter 27 Utility AI | Same file, lines 18805–19055 |
| Chapter 28 Memory Retrieval | Same file, lines 19059–19279 |

## Requirement table

| Requirement | Canonical source | Exact value/formula | Confidence |
|-------------|------------------|---------------------|------------|
| Actor tiers | `Source_of_Truth_v1.2.md:L18334-L18344` | Hero → Active → Relevant → Dormant → Archived | High |
| Tier ceilings | `Source_of_Truth_v1.2.md:L20858` | Hero 16 / Active 200 / Relevant 2000 / Dormant ∞ / Archived ∞ | High |
| Demotion grace | `Source_of_Truth_v1.2.md:L18492-L18495`, `L20859` | 5 min / 24 h / 7 d / 30 d | High |
| Retention→tier eligibility | `Source_of_Truth_v1.2.md:L20860` | >0.7 Hero / >0.5 Active / >0.3 Relevant / ≤0.3 Dormant–Archived | High |
| Gravity→tier eligibility | `Source_of_Truth_v1.2.md:L20861`, `L18527-L18530` | >0.8 Hero / >0.5 Active / >0.2 Relevant | High |
| Retention formula | `Source_of_Truth_v1.2.md:L18660-L18678`, `L20845` | R = G×(1+0.5C)×(1+0.5P)×D/2.25 clamped 0–1 | High |
| Retention bands | `Source_of_Truth_v1.2.md:L18686-L18692`, `L20848` | ≥0.8 keep / 0.6–0.8 light / 0.4–0.6 compress / 0.2–0.4 archive / <0.2 deletable | High |
| Forget threshold | `Source_of_Truth_v1.2.md:L19197`, `L20848` | retention < 0.2 → archive path; P<0.01 for 30d connectivity signal | High |
| Utility dimensions | `Source_of_Truth_v1.2.md:L18859-L18867` | Survival, Goal, Pressure relief, Stress, Relationship, Resource, Memory avoidance | High |
| Utility formula | `Source_of_Truth_v1.2.md:L18903-L18904`, `L20867` | U = Σ(score×weight)/Σ(weight), bounded 0–100 | High |
| Base weights | `Source_of_Truth_v1.2.md:L18937-L18943`, `L20868` | 100/50/30/20/40/25/15 + dynamic modifiers | High |
| Whim noise | `Source_of_Truth_v1.2.md:L18953`, `L20869` | ±0.5 seeded RNG before comparison | High |
| Tie window | `Source_of_Truth_v1.2.md:L18955`, `L20870` | 0.01 after noise | High |
| Memory probability | `Source_of_Truth_v1.2.md:L19123-L19133` | P(m)=(R×E×C×P_base)/Σ(all memories) | High |
| Working-memory sizes | `Source_of_Truth_v1.2.md:L19209-L19214`, `L20877` | Hero 7 / Active 5 / Relevant 3 / Dormant 1 | High |
| Base retrieval probability | `Source_of_Truth_v1.2.md:L19131`, `L20879` | defining 0.9 / major 0.5 / minor 0.01 | High |
| Emotional bias | `Source_of_Truth_v1.2.md:L19157-L19160`, `L20880` | 2.0 / 1.5 / 1.0 / 0.5 | High |
| Pattern bonus | `Source_of_Truth_v1.2.md:L19173`, `L20881` | P_base × (1 + log10(count)) | High |
| Sampling method | `Source_of_Truth_v1.2.md:L19133` | Weighted random to fill working_memory_size | High |

## Canon conflicts

None unresolved between Appendix A and chapter bodies for Ch 25–28 in v1.2.

## Test status

Non-live suite: **570 passed** (34 live deselected) after foundation integration hook.

## Deployment

Not merged. Not deployed.