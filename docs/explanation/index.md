---
icon: lucide/compass
template: section-index.html
description: How spectrafit-core's model composition DAG, parameter model, and solver front-end actually work under the hood.
tags:
  - NIST StRD
  - Models
  - Solvers
cta:
  text: "Read the DAG model"
  link: explanation/model-composition-dag/
cards:
  - title: "Model composition (DAG IR)"
    icon: lucide/git-fork
    link: explanation/model-composition-dag/
  - title: "Parameter model"
    icon: lucide/sliders
    link: explanation/parameter-model/
  - title: "Solver front-end & post-fit statistics"
    icon: lucide/route
    link: explanation/solver-selection/
  - title: "NIST StRD validation"
    icon: lucide/badge-check
    link: explanation/nist-validation/
---

# Explanation { .sf-section-hero__title }

<p class="sf-section-hero__tagline">
The conceptual model behind spectrafit-core: how model composition works as
a directed acyclic graph (DAG), the parameter model, and how the solver
front-end forms its residual and Jacobian and derives its post-fit
statistics. Background, not step-by-step instructions. For how
<code>solver="auto"</code> actually routes a graph to VarPro or TRF, and when to override it, see
<a href="../how-to/choosing-a-solver/">Choosing a Solver</a>.
</p>
