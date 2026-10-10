# Project Plan

## Goal

Build a simple community organizing and volunterring application for local non-profits.

The goal is to essentially port the functionality from https://github.com/JumboCode/boston-community-pediatrics into a
generic open-source (AGPL licensed) project that can be used by any non-profit. Opting for a very simple and stable
tech stach that's both flexable and able to handle low-volume small non-profit sites.

Ideally the whole project run on a low-cost VPS.

## Tech-stack

- [thumbor](https://github.com/thumbor/thumbor) for image resizing
- [caddy](https://github.com/caddyserver/caddy) for HTTP server
- [django](https://www.djangoproject.com/) for a web framework and application code
    - authentication via django-allauth
    - email backend connected to *TBD*
        - Mailchimp? Sendgrid? Can be a SaaS offering and not IaaS (via SMTP server), the extras of delivery status and
          email templating is probably wanted.
    - [bootstrap 5 with vite](https://getbootstrap.com/docs/5.3/getting-started/vite/) for the frontend assets

