# TODO

- [ ] Build demo site, create documentation for how everything works
- [ ] Create a custom styled site, ensure everything is working as expected and will work for real non-profits
- [ ] Document cost breakdown for various different providers, including more docs for 3rd-party SaaS/IaaS requirements
-
## Ideas

- [ ] Create a full serverless implementation using AWS CDK
    - optimized for larger non-profits and for-profit institutions where constraints are different
    - django-allauth to Auth0 for IsP
    - FastAPI or NestJS for framework, run on AWS Lamda
    - SQS, Lamda, and SES for scheduled events
    - Aurora or DynamoDB for database (skip RDBS)
    - Ensure "scale-to-zero" architecture

