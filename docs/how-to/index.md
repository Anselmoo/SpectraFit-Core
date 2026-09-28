---
icon: lucide/wrench
template: section-index.html
description: Task-focused guides — picking a solver, adding a model kernel, and the gallery's task recipes for fixing, bounding, tying and weighting parameters.
tags:
  - Models
  - Solvers
cta:
  text: "Pick the right solver"
  link: how-to/choosing-a-solver/
cards:
  - title: "Adding a model"
    icon: lucide/puzzle
    link: how-to/adding-a-model/
  - title: "Choosing a solver"
    icon: lucide/git-compare
    link: how-to/choosing-a-solver/
  # The nine cards below point into `tutorials/gallery/`, not into this
  # directory. Read by Diataxis mode, those pages are already task-shaped
  # how-tos ("Holding a Parameter Fixed", "Robust Fitting Against Outliers") --
  # they were simply filed in the gallery bucket with the true tutorials and the
  # explanation-style comparisons. Surfacing them here is deliberate: this repo
  # configures no redirect mechanism, so physically moving them would break
  # every external link and force a rewrite across ~7k internal refs, for no
  # reader benefit that a card does not already deliver.
  - title: "Holding a parameter fixed"
    icon: lucide/lock
    link: tutorials/gallery/fixed_params/
  - title: "Bounded fitting"
    icon: lucide/ruler
    link: tutorials/gallery/bounded_fitting/
  - title: "Sharing parameters across peaks"
    icon: lucide/link-2
    link: tutorials/gallery/shared_params/
  - title: "Sigma-weighted fitting"
    icon: lucide/weight
    link: tutorials/gallery/weighted_fitting/
  - title: "Robust fitting against outliers"
    icon: lucide/shield
    link: tutorials/gallery/robust_fitting/
  - title: "Confidence intervals"
    icon: lucide/sigma
    link: tutorials/gallery/confidence_intervals/
  - title: "Escaping local minima"
    icon: lucide/scan-search
    link: tutorials/gallery/global_optimizer/
  - title: "Multi-dataset joint fitting"
    icon: lucide/layers
    link: tutorials/gallery/multi_dataset/
  - title: "N-dimensional fitting"
    icon: lucide/boxes
    link: tutorials/gallery/3d_fitting/
---

# How-to guides { .sf-section-hero__title }

<p class="sf-section-hero__tagline" markdown>
Task-focused answers for a specific job. Two guides live here; the rest are
task recipes that sit in the [gallery](../tutorials/gallery/index.md) alongside
the worked examples, and are linked below so you do not have to know that.
Assumes you've already completed [Getting Started](../getting-started/index.md).
</p>
