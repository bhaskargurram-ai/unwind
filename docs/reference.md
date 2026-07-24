---
title: API reference
---

# API reference

The core typed protocol objects live in `unwind.types` and are defined *first*, because every other module depends on them. All comparisons on the ordinal enums are meaningful (`R0 < R4`), which the [metrics](benchmark.md) rely on.

This page is generated from the source docstrings by [mkdocstrings](https://mkdocstrings.github.io/). It requires the `mkdocstrings[python]` handler from the `[docs]` extra.

## `unwind`

::: unwind
    options:
      show_root_heading: true
      members: false

## Core types

::: unwind.types
    options:
      show_root_heading: false
      show_source: true
      members_order: source
      heading_level: 3
