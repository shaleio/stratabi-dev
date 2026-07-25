<!--
AUTHORITATIVE LICENSE NOTICE
This file is the text of the Shaleio Guild Community License (SGCL), Version 1.0.
The canonical execution copy is Guild_Community_License_SK_070326_d05.docx, held by
Shaleio LLC and included in this repository as LICENSE.docx. This Markdown rendering
reproduces the license text; Word auto-numbering of sub-sections is not re-rendered
here and should be read against the canonical .docx. Do not edit this text.
-->

SHALEIO GUILD COMMUNITY LICENSE

Version: 1.0

Last revised: July 2, 2026

Effective Date: July 2, 2026

Copyright: © 2026 Shaleio LLC. All rights reserved.

Licensor: Shaleio LLC

Software: StrataBI Developer Edition / Community Edition

## ARTICLE 1 – PURPOSE AND SCOPE

Purpose. This Shaleio Guild Community License (the “License”) allows developers, individuals, and organizations to inspect, use, modify, and extend the StrataBI Developer Edition under defined community and self-managed deployment conditions, while preserving Shaleio’s rights to commercialize StrataBI Enterprise, official modules, managed deployment patterns, support, and related services. This License is intended to permit useful developer and self-managed use of StrataBI while prohibiting resale, white-labeling, managed service offerings, competing commercial offerings, and use of designated enterprise deployment patterns without a separate commercial license.

Developer Edition positioning. The Developer Edition is intended primarily as a developer and evaluation tool — run on a developer’s local machine, on an AWS WorkSpaces virtual desktop, or via the AWS CLI / AWS CloudShell against the developer’s own AWS account — for building, testing, and operating Modules and dashboards. It is not provided as a turnkey hosting platform, a multi-tenant service, or a means of delivering StrataBI’s functionality to unaffiliated third parties. Deployment patterns reserved for the Enterprise Edition, including Managed Application Hosting, require a separate commercial license.

## ARTICLE 2 – DEFINITIONS

“Shaleio,” “Licensor,” “we,” “our,” or “us” means Shaleio LLC, a Florida limited liability company.

“You,” “your,” or “Licensee” means the individual or legal entity exercising rights under this License.

“Software” means the StrataBI Developer Edition, StrataBI Community Edition, source code, object code, documentation, examples, schemas, configuration templates, and other materials made available by Shaleio under this License.

“StrataBI Enterprise” or “Enterprise Edition” means any paid, commercial, enterprise, hosted, managed, support-included, or separately licensed version of StrataBI, including enterprise deployment materials, commercial modules, enterprise-only features, and support services.

“Developer Edition” or “Community Edition” means the version of StrataBI distributed under this License for developer evaluation, educational, personal, internal, and self-managed use, excluding Enterprise Features unless expressly stated by Shaleio.

“Primary Runtime” means the main StrataBI application runtime, user-facing web runtime, API runtime, orchestration runtime, dashboard runtime, or other primary service layer responsible for serving or operating StrataBI as an application.

“Module” means a software package, connector, extension, block, dashboard component, execution template, workflow, integration, or related add-on designed to run with, call into, extend, or be loaded by StrataBI.

“Official Module” means a Module published, certified, sold, maintained, or expressly designated by Shaleio as official, certified, enterprise, guild-approved, or otherwise endorsed.

“Third-Party Module” means a Module authored by someone other than Shaleio that has not been expressly designated by Shaleio as an Official Module.

“Enterprise Features” means paid or commercially reserved functionality, including but not limited to: enterprise role-based access control (RBAC); the administrative console; enterprise SSO/SAML/OIDC packaging; the AI-assisted dashboard builder; dashboards-as-code / git-registry administrative override; favorites and pinned-dashboard management; commercial and managed deployment automation; official enterprise Modules; license-gated features; the StrataHQ entitlement, licensing, signing, and account-binding mechanisms and related tooling; support tooling; marketplace distribution features; commercial warranties; or other features identified by Shaleio as enterprise-only. Enterprise Features are not licensed under this License and require a separate commercial license, regardless of deployment target.

“Managed Application Hosting” means a managed, serverless, or fully managed application/container hosting service used to run the Primary Runtime where the underlying compute host management is substantially abstracted away from you. Examples include AWS Fargate, Amazon EKS on Fargate, AWS App Runner, AWS Lightsail Container Services, and substantially similar services.

“Self-Managed Infrastructure” means infrastructure where you remain materially responsible for provisioning, operating, patching, scaling, and maintaining the compute environment. Examples include local development machines, on-premises servers, self-managed virtual machines, Amazon EC2, ECS on EC2, EKS using EC2 worker nodes, and self-managed Kubernetes clusters.

“Commercialization” means selling, reselling, renting, leasing, sublicensing, hosting, white-labeling, embedding, bundling, distributing for consideration, offering as a service, offering as a managed service, or otherwise monetizing the Software or substantially similar functionality derived from the Software.

“Competing Offering” means any product, service, hosted platform, managed platform, commercial distribution, marketplace listing, appliance, or other offering that (a) competes with StrataBI or the Enterprise Edition, or (b) makes the Software’s substantial functionality available to, or operates the Software on behalf of, unaffiliated third parties. For clarity, a Competing Offering does not include your own internal business use of the Software, or your presentation of dashboards, reports, or artifacts produced by the Software to your own customers, provided you do not give those third parties access to operate, deploy, configure, or build upon the Primary Runtime itself.

“Shaleio Technology” means the Software, documentation, deployment templates, schemas, designs, inventions, know-how, source code, object code, user interfaces, workflows, modules, connectors, improvements, modifications, derivatives, and related intellectual property owned or controlled by Shaleio.

“Shaleio Marks” means “Shaleio,” “StrataBI,” “Shaleio Guild,” “Guildmaster,” “Guild Approved,” the associated logos, certification marks, product names, and any other trademarks, service marks, trade names, or branding controlled by Shaleio.

“Permitted Purposes” means the purposes for which you are licensed to use the Software, as enumerated in Article 4. Any use outside the Permitted Purposes is outside the scope of this License and constitutes a material breach.

“Authorized Developer Environment” means a computing environment that you operate for your own development, evaluation, or internal business use and for which you remain materially responsible, including: a local development machine or workstation; an AWS WorkSpaces (or substantially similar managed virtual-desktop) instance assigned to an individual user; an AWS CloudShell or AWS CLI session operated by you; and Self-Managed Infrastructure as defined in Section XII of this Article. An Authorized Developer Environment does not include Managed Application Hosting used to serve or operate the Primary Runtime for others.

“Affiliate” means any entity that directly or indirectly controls, is controlled by, or is under common control with you, where “control” means ownership or control of more than fifty percent (50%) of the voting interests or the right to direct management.

“Unaffiliated third party” means any person or entity that is neither you nor your Affiliate.

“Trade Secrets” means information within the Software that derives independent economic value from not being generally known and that Shaleio takes reasonable measures to keep secret, including the source code, object code, and signed runtime artifacts of portions of the Software designated by Shaleio as confidential or proprietary, Entitlement Service design, non-public Modules, and related deployment materials. The Developer/Community Edition source code distributed under this source-available license is not a Trade Secret except as specifically designated by Shaleio.

“Confidential Information” means non-public information disclosed by Shaleio to you that is marked confidential or reasonably should be understood to be confidential, including Trade Secrets, technical designs, algorithms, architectures, security information, vulnerability reports, incident details, business plans, strategies, non-public product roadmaps, and any other information identified as confidential or proprietary.

## ARTICLE 3 – LICENSE GRANT

License rights. Subject to your compliance with this License, Shaleio grants you a non-exclusive, worldwide, royalty-free, non-transferable, non-sublicensable license to:

Use and run the Software for Permitted Purposes.

Copy the Software as reasonably necessary for Permitted Purposes.

Modify the Software for Permitted Purposes.

Create Modules for use with the Software.

Internally deploy the Software on Self-Managed Infrastructure.

Distribute unmodified or modified copies of the Software only as expressly permitted by this License.

All rights not expressly granted are reserved by Shaleio.

Patent license. Subject to your compliance with this License, and solely to the extent necessary to exercise the rights granted in Section 1 of this Article for Permitted Purposes, Shaleio grants you a non-exclusive, worldwide, royalty-free, non-transferable, non-sublicensable license under any patent claims owned or controlled by Shaleio that are necessarily infringed by the unmodified Software as provided by Shaleio. This patent license does not extend to:

Any use outside the Permitted Purposes.

Commercialization, a Competing Offering, or Managed Application Hosting of the Primary Runtime.

Modifications to the Software, or combinations of the Software with other software not provided by Shaleio, where the infringement is caused by the modification or combination rather than the unmodified Software alone.

Patent defensive termination. If you, or any entity you control, initiate or knowingly support a patent claim, cross-claim, or counterclaim alleging that the Software or any Shaleio product infringes a patent, all licenses granted to you under this License (including Section 3 of this Article) terminate automatically as of the date such action is filed. For purposes of this Section, “knowingly support” means providing material financial support or joining as a co-plaintiff, but does not include compelled testimony, amicus briefs, or purely defensive counterclaims strictly in response to a prior suit by Shaleio against you.

## ARTICLE 4 – PERMITTED PURPOSES

Enumerated permitted purposes. You may use the Software under this License for the following purposes:

Personal, non-commercial use.

Educational, training, and academic use.

Internal evaluation and assessment.

Development, testing, and quality assurance activities.

Creating, testing, and maintaining Modules.

Internal business use on Self-Managed Infrastructure for your own organization.

Self-managed proof-of-concept deployments.

Other uses expressly approved in writing by Shaleio.

Permitted deployment targets. For avoidance of doubt, the following Primary Runtime deployment and operating targets are permitted under this License when used for Permitted Purposes and not as part of a prohibited Commercialization, Competing Offering, or managed service:

Local development machines, developer laptops, and workstations.

AWS WorkSpaces or substantially similar managed virtual desktop operated by you.

AWS CloudShell or AWS CLI sessions operated by you.

On-premises servers.

Self-managed virtual machines.

Amazon EC2 instances.

ECS on EC2.

EKS using EC2 worker nodes.

Self-managed Kubernetes clusters.

Equivalent self-managed infrastructure.

Enterprise Feature exclusion. Permission to run the Primary Runtime on any of the targets in Section 2 of this Article is permission to run the Developer Edition’s non-Enterprise functionality only. None of the foregoing permits you to operate, enable, or provide Enterprise Features; Enterprise Features require a separate commercial license regardless of deployment target (see Article 5, Sections 5 and 16).

## ARTICLE 5 – RESTRICTIONS

No resale or commercial distribution. You may not sell, resell, rent, lease, sublicense, commercially distribute, or otherwise commercialize the Software without a separate written commercial license from Shaleio.

No hosted or managed service. You may not provide the Software, modified versions of the Software, or substantially similar functionality derived from the Software to third parties as a hosted service, managed service, SaaS offering, platform service, bureau service, internal platform for unaffiliated third parties, or similar service without a separate written commercial license from Shaleio.

No white-labeling. You may not white-label, rebrand, obscure the origin of, or present the Software as your own commercial product or service without a separate written commercial license from Shaleio.

No competing offering. You may not use the Software to create, operate, support, or offer a Competing Offering without a separate written commercial license from Shaleio.

No Enterprise Feature circumvention or enablement. You may not unlock, enable, activate, bypass, remove, disable, obscure, circumvent, or work around any license check, feature gate, entitlement check, notice, access control, or other technical limitation intended to distinguish the Developer Edition from StrataBI Enterprise. You also may not add, build, port, backport, reimplement, recreate, restore, or otherwise cause the Developer Edition to provide, any Enterprise Feature, whether by modifying the Software, supplying additional code or configuration, combining the Software with other software, or by any other means. Enterprise Features require a separate commercial license.

No Managed Application Hosting for the Primary Runtime. You may not deploy, operate, host, or make available the Primary Runtime using Managed Application Hosting without a separate commercial license. This restriction targets services in which the underlying compute host management is substantially abstracted away from you, whether offered by AWS or by any other provider, now existing or later created; it is the scope and nature of the service, not the specific product name, that controls. Notwithstanding any provision herein to the contrary:

Developer environment clarification. For the avoidance of doubt, running the Software for your own development, evaluation, or internal use on an Authorized Developer Environment — including a local machine, an AWS WorkSpaces virtual desktop, or an AWS CloudShell / AWS CLI session — is permitted and is not Managed Application Hosting.

Prohibited services. For avoidance of doubt, the following are not permitted for the Primary Runtime under this License without a separate commercial license:

AWS Fargate.

Amazon EKS on Fargate.

AWS App Runner.

AWS Lightsail Container Services.

Substantially similar managed, serverless, or fully managed container/application hosting services.

Module service calls. This Section does not prohibit a Module from calling AWS Lambda, Athena, Bedrock, S3, Glue, EMR, DynamoDB, or similar cloud services as part of a permitted StrataBI workflow, provided the Primary Runtime itself is not deployed in violation of Article 5.

No removal of notices. You may not remove, obscure, or alter copyright notices, license notices, attribution notices, proprietary notices, product notices, or notices identifying Shaleio as the source of the Software.

No trademark license. This License does not grant rights to use Shaleio Marks except as necessary to truthfully identify the Software in accordance with Article 9.

No unlawful or prohibited use. You may not use the Software in violation of applicable law, export control restrictions, sanctions restrictions, anti-corruption laws, or any rights of third parties.

No third-party-facing or multi-tenant operation. You may not operate the Primary Runtime as a multi-tenant system or make the Primary Runtime available to unaffiliated third parties to access, operate, configure, deploy, or build upon, whether or not for a fee. Presenting dashboards, reports, or artifacts produced by the Software to your own customers is permitted, provided those third parties are not given access to the Primary Runtime itself.

No circumvention of deployment restrictions. You may not wrap, proxy, embed, containerize, repackage, or interpose intermediary software around the Software for the purpose of operating or making available the Primary Runtime through Managed Application Hosting, or to third parties, in a manner that would otherwise require a separate commercial license.

No AI/ML training to replicate the Software. You may not use the Software, its source code, schemas, or documentation as training data, or for fine-tuning, model distillation, or other machine-learning purposes intended to produce a product, model, or service that reproduces or substantially replicates the Software or its functionality or that would constitute a Competing Offering. For clarity, internal research or experimentation that does not lead to a Competing Offering or Commercialization is not prohibited by this Section.

No benchmarks or competitive disclosures without approval. You may not publish benchmarks, performance comparisons, or competitive analyses of the Software without Shaleio’s prior written approval, except to the extent such a restriction is prohibited by applicable law. Notwithstanding the foregoing, you may conduct internal benchmarking and security testing for your own evaluation, procurement, and operational purposes under reasonable confidentiality obligations, and you may disclose such benchmarks to internal stakeholders or regulators under confidentiality obligations. Any permitted benchmarks must fairly and accurately describe test conditions.

No turnkey appliance or unauthorized bundling. You may not distribute or make available the Software as a pre-configured appliance, virtual machine image, container image, or bundled product intended to let third parties operate the Primary Runtime without separately accepting this License or a commercial license.

Scope discipline. Any use of the Software outside the Permitted Purposes, or in excess of the rights expressly granted, is prohibited and constitutes a material breach of this License.

No Enterprise Features on permitted deployment targets. The deployment targets permitted for the Developer Edition under Article 4 — including local machines, Authorized Developer Environments, Amazon EC2, ECS on EC2, EKS or other Kubernetes on EC2 worker nodes, self-managed virtual machines, on-premises servers, and equivalent Self-Managed Infrastructure — are licensed for the Developer Edition’s non-Enterprise functionality only. Permission to run the Primary Runtime on a given target is not permission to operate Enterprise Features on that target. Operating, enabling, restoring, recreating, or making available any Enterprise Feature on Self-Managed Infrastructure (expressly including Amazon EC2 and Kubernetes), or on any other target, without a separate commercial license, is prohibited and is a material breach of this License, regardless of whether the underlying deployment target is otherwise permitted. This restriction exists because permitted self-managed targets such as EC2 and Kubernetes are not subject to the managed-hosting limit in Section 6 of this Article; the Enterprise-Feature boundary applies to them all the same.

## ARTICLE 6 – EXPORT CONTROL, SANCTIONS, AND COMPLIANCE

Compliance with export laws. You must comply with all applicable export control, sanctions, anti-corruption, and trade compliance laws, including but not limited to the U.S. Export Administration Regulations (EAR), International Traffic in Arms Regulations (ITAR), and regulations administered by the Office of Foreign Assets Control (OFAC), the EU sanctions framework, and the UK sanctions regime.

Your representation. You represent and warrant that:

You are not located in, organized under the laws of, or owned or controlled by persons or entities in any country or region subject to comprehensive U.S. sanctions (currently Cuba, Iran, North Korea, Syria, or the Crimea, Donetsk, or Luhansk regions of Ukraine).

You are not identified on any U.S. government restricted party list, including the Specially Designated Nationals and Blocked Persons List, the Entity List, or the Denied Persons List, or any similar list maintained by the EU, UK, or other applicable jurisdiction.

You will not export, re-export, transfer, or provide access to the Software, directly or indirectly, to any prohibited destination, entity, or person.

You will not use the Software for any prohibited end use, including development, production, or use of nuclear, chemical, or biological weapons, or missile technology.

Notification of restricted status. You will notify Shaleio immediately in writing if you become a denied or restricted party under any applicable export or sanctions law, or if your ownership, control, or operations change in a manner that would cause you to become subject to export or sanctions restrictions.

Suspension for sanctions or export concerns. Shaleio may suspend all rights granted under this License, without liability, if Shaleio reasonably believes that continued performance would violate applicable export control or sanctions laws, or if you fail to cure a breach of this Article within ten (10) days after written notice.

## ARTICLE 7 – MODULES

Your Modules. Subject to Section 3 of this Article, you retain ownership of original Third-Party Modules you create.

Module independence. A Module may be licensed separately by its author if the Module does not include, copy, or create an unauthorized derivative distribution of the Software and does not violate this License.

No implied certification. You may not represent a Module as official, certified, guild-approved, endorsed, compatible with enterprise deployments, or supported by Shaleio unless Shaleio expressly authorizes that designation in writing.

Official Modules. Official Modules may be subject to separate commercial, marketplace, enterprise, or module-specific license terms. This License does not grant rights to paid Official Modules unless Shaleio expressly distributes those modules under this License.

Marketplace terms reserved. Marketplace distribution, certification, revenue sharing, bounty contributions, contributor royalties, official listing, consulting deployment fees, and related marketplace rights are not governed by this License unless Shaleio later incorporates separate marketplace terms.

## ARTICLE 8 – DISTRIBUTION OF MODIFIED VERSIONS

Distribution conditions. You may distribute modified versions of the Software only if all of the following are true:

The distribution is not Commercialization.

The distribution does not create a Competing Offering.

The distribution is under this same License.

You preserve all copyright, license, attribution, and proprietary notices.

You clearly mark your changes and indicate that the Software has been modified.

You do not use Shaleio Marks except for truthful attribution.

You do not imply endorsement, certification, support, or affiliation by Shaleio.

Confusing branding. Shaleio may require you to stop using any name, branding, packaging, or presentation that creates confusion with official Shaleio products or services.

Remedy for non-compliant distribution. Non-compliant distribution constitutes a material breach subject to immediate termination under Article 14.

## ARTICLE 9 – CONTRIBUTIONS TO SHALEIO PROJECTS

Contribution license. If you submit a contribution, pull request, patch, issue-attached code, documentation change, example, configuration, or other material to a repository, channel, or project controlled by Shaleio, you represent that you have the right to submit it and you grant Shaleio a perpetual, irrevocable, worldwide, royalty-free, sublicensable, transferable, non-exclusive license to use, reproduce, modify, distribute, sublicense, sell, support, relicense, and commercialize that contribution as part of Shaleio products and services.

Retention of ownership. This Article does not transfer ownership of your original contribution to Shaleio. It grants Shaleio the rights necessary to maintain, distribute, and commercialize Shaleio products that include the contribution.

Contributor representations. By submitting a contribution, you represent that:

You have obtained all necessary rights from your employers, co-authors, or other relevant parties to grant the license in Section 1 of this Article.

The contribution is your original work or you have sufficient rights to submit it under the terms of this Article.

You acknowledge that no compensation is owed for contributions under this License.

Separate contributor agreement. Shaleio may later require a separate contributor license agreement for certain contributions.

## ARTICLE 10 – ATTRIBUTION AND TRADEMARKS

Required retention. You must retain the following in all copies and permitted distributions of the Software:

Copyright notices.

This License.

Attribution notices.

Notices identifying Shaleio as the licensor.

Notices identifying modified versions as modified.

Permitted nominative use. You may use Shaleio Marks only to accurately state that your work uses, extends, or is compatible with StrataBI, provided you do not imply endorsement, sponsorship, certification, or affiliation. Examples of permitted nominative use include:

“Module for StrataBI Developer Edition.”

“Built to run with StrataBI.”

“Compatible with StrataBI Community Edition.”

Prohibited trademark use. Examples of prohibited use include:

“Official StrataBI Module” without written approval.

“Guild Approved” or “Guildmaster Certified” without written approval.

Using Shaleio logos without written approval.

Branding a fork or competing product in a way likely to confuse users.

Quality control. Any permitted use of Shaleio Marks must maintain the quality standards associated with Shaleio Marks and comply with Shaleio’s trademark usage guidelines, if provided.

## ARTICLE 11 – THIRD-PARTY SOFTWARE AND OPEN SOURCE

Third-party components. The Software may include or depend on third-party software, libraries, services, or materials subject to separate license terms. Those third-party terms govern your use of the applicable third-party materials. This License does not grant rights beyond those Shaleio is legally able to grant.

Open source license precedence. To the extent any open source component is governed by its own open source license, that open source license governs your use of that component. In the event of any conflict between this License and an applicable open source license regarding the specific open source component, the open source license will control as to that component to the extent required by such license.

Your responsibility for third-party services. You are solely responsible for:

Obtaining and maintaining accounts, licenses, and access to third-party services and APIs used with the Software.

Compliance with third-party terms of service, acceptable use policies, and licensing requirements.

Any data shared with or processed by third-party services through your use of the Software.

## ARTICLE 12 – CLOUD COSTS AND THIRD-PARTY SERVICES

Your sole responsibility. You are solely responsible for all infrastructure, cloud, hosting, storage, data transfer, compute, query, AI model, logging, monitoring, and third-party service costs incurred from your use of the Software.

No Shaleio responsibility. Shaleio is not responsible for AWS, cloud provider, marketplace, third-party API, or infrastructure charges arising from your use of the Software.

## ARTICLE 13 – SUPPORT, UPDATES, AND MAINTENANCE

No support obligation. Shaleio has no obligation to provide support, maintenance, hosting, patches, updates, security fixes, professional services, deployment assistance, or consulting under this License.

Separate commercial agreements. Any support, maintenance, professional services, commercial deployment assistance, or access to Shaleio personnel must be separately agreed in writing and requires a separate commercial license.

Updates at Shaleio’s discretion. Shaleio may, but is not obligated to, provide updates or patches. Use of new versions will be governed by the then-current license terms accompanying that version unless you choose to continue using the prior version under its original license.

Deprecation and discontinuation. Shaleio reserves the right to modify, suspend, or discontinue the Software or any features, including the Developer Edition, at any time with or without notice. Shaleio will use reasonable efforts to give ninety (90) days’ advance notice of material discontinuations where commercially practicable. Shaleio will not be liable for such changes, modifications, suspensions, or discontinuations.

## ARTICLE 14 – PRIVACY, DATA, AND SECURITY

Your data responsibility. You are responsible for all data, credentials, secrets, tokens, keys, prompts, queries, logs, metadata, outputs, and other materials you process using the Software. You are responsible for configuring access controls, identity providers, cloud policies, encryption, logging, monitoring, retention, deletion, and compliance controls appropriate for your environment.

No Shaleio data rights. Shaleio does not receive rights to your data merely because you use the Software under this License.

No data transmission by default. The Software does not transmit your data back to Shaleio by default. You acknowledge that you are solely responsible for the security and privacy of your data.

Data protection compliance. You are solely responsible for compliance with applicable data protection laws, including but not limited to the General Data Protection Regulation (GDPR), UK GDPR, California Consumer Privacy Act (CCPA), and other privacy laws. You are the data controller for any personal data you process using the Software and bear all compliance obligations.

Security incident reporting. You must promptly notify Shaleio of any security incident involving the Software that may affect Shaleio, the Software, Shaleio Technology, Trade Secrets, or other users.

Recommended configurations. Shaleio may provide recommended security configurations, deployment guidance, and best practices. You acknowledge that such recommendations are provided as guidance only and must be evaluated and approved by you against your own security policies, regulatory requirements, and risk tolerance. Shaleio is not responsible for your configuration choices or security posture.

## ARTICLE 15 – AUDIT AND COMPLIANCE VERIFICATION

Record-keeping obligation. You will maintain accurate records of your use, deployment, and distribution of the Software, including deployment configurations, environment details, and usage logs, for a period of three (3) years from the date of such use, deployment, or distribution.

Compliance certification. Upon reasonable written request not more than once per twelve-month period, you will certify in writing that your use of the Software complies with this License, including license scope, Permitted Purposes, deployment restrictions, and field-of-use restrictions.

Audit rights. If Shaleio has a reasonable basis to believe you are using the Software outside the licensed scope, exceeding Permitted Purposes, deploying on prohibited Managed Application Hosting, enabling Enterprise Features, or otherwise materially violating the terms of this License, Shaleio may, upon at least thirty (30) days’ prior written notice:

Request records reasonably necessary to verify compliance, including deployment configurations, environment details, account identifiers, and usage information.

Conduct a remote audit during your normal business hours in a manner designed to minimize disruption to your operations.

Require that any on-site audit be performed by an independent third-party auditor under a mutual nondisclosure agreement.

Audit confidentiality and security. Any audit conducted under this Article will:

Comply with your reasonable security and confidentiality requirements.

Be limited in scope to information necessary to verify compliance with this License.

Be conducted by personnel bound by confidentiality obligations.

Result in an audit report provided to both parties summarizing findings without disclosing your broader systems or business information beyond what is necessary to identify compliance issues.

Audit costs. Each party will bear its own costs of the audit, except that if an audit shows use outside the licensed scope, unlicensed Commercialization, use of prohibited Managed Application Hosting, enablement of Enterprise Features, or other material breach, you must promptly:

Cure the breach.

Reimburse Shaleio for reasonable audit costs incurred.

Pay commercial license fees for any unlicensed use at Shaleio’s then-current rates, calculated from the date of first unlicensed use or twelve (12) months prior to the audit notice, whichever is later.

Cooperation. You will cooperate with Shaleio’s reasonable audit requests and provide timely access to relevant systems, records, and personnel.

## ARTICLE 16 – ACCESSIBILITY AND REGULATORY USE LIMITATIONS

No accessibility warranty. Shaleio does not warrant that the Software’s user interfaces or documentation conform to any specific accessibility standards (such as WCAG, Section 508, ADA, or similar requirements). You are solely responsible for evaluating whether the Software meets your accessibility requirements.

Regulated and high-risk use. You are solely responsible for determining whether use of the Software in regulated, safety-critical, or high-risk contexts complies with applicable laws and standards. You acknowledge that:

Shaleio does not design or certify the Software for compliance with specific sectoral regulations (such as HIPAA, PCI-DSS, medical device regulations, aviation safety standards, FDA regulations, FINRA requirements, or defense industry standards).

The Software is not designed, tested, or certified for use in high-risk, safety-critical, life-sustaining, medical, defense, financial services, government, or other regulated environments where failure could result in death, personal injury, property damage, financial loss, or regulatory penalty.

You must conduct your own compliance assessment and risk analysis before deploying the Software in any regulated or high-risk environment.

Use of the Software in highly regulated industries or high-risk contexts may require a separate written agreement with Shaleio addressing specific regulatory compliance commitments, certifications, indemnities, and enhanced support.

## ARTICLE 17 – OWNERSHIP AND INTELLECTUAL PROPERTY

Shaleio ownership. Shaleio owns and retains all right, title, and interest in and to the Software, including all intellectual property rights. No rights are transferred except the limited license rights expressly granted in this License.

Your ownership. You own your data and your original Modules that do not incorporate the Software, subject to Shaleio’s rights in the underlying Software, Official Modules, and any Shaleio Technology.

No implied licenses. No licenses or rights are granted by implication, estoppel, usage of trade, or course of dealing. You acknowledge that all rights not expressly granted under this License are reserved to Shaleio.

Generic know-how. Nothing in this License restricts your personnel from using generic skills, knowledge, and experience gained through normal use of the Software, provided such use does not involve disclosure or use of the Software, Trade Secrets, or Confidential Information.

## ARTICLE 18 – CONFIDENTIALITY AND TRADE SECRETS

Confidential Information protection. You must:

Use Confidential Information only to exercise the rights granted under this License.

Protect Confidential Information using at least reasonable care and no less than the care you use to protect your own confidential information of similar nature.

Not disclose Confidential Information to any third party except as permitted by this License.

Permitted disclosures. You may disclose Confidential Information:

To your employees, contractors, advisors, and legal counsel who have a need to know and who are bound by confidentiality obligations at least as protective as those in this License.

To the extent required by law, regulation, court order, or governmental authority, provided you give Shaleio prompt written notice (where legally permitted) and reasonable opportunity to seek a protective order or other appropriate remedy.

Exceptions. The confidentiality obligations in this Article do not apply to information that you can demonstrate:

Is or becomes publicly available through no fault or breach by you.

Was already lawfully known to you without restriction before disclosure by Shaleio.

Was independently developed by you without use of or reference to Shaleio’s Confidential Information.

Was lawfully received from a third party without restriction and without breach of any obligation to Shaleio.

Trade Secrets protection. You acknowledge that the Trade Secrets constitute some of Shaleio’s most valuable confidential and proprietary information. You will protect Trade Secrets with the highest degree of care and will not disclose, use, reverse engineer, decompile, disassemble, or permit access to Trade Secrets except as expressly authorized by this License. To the extent applicable law prohibits restrictions on reverse engineering for interoperability purposes, you will first request the necessary interface information from Shaleio before engaging in any reverse engineering.

Duration. Confidentiality obligations will continue for five (5) years from the date of disclosure, except that obligations regarding Trade Secrets will continue for so long as the information remains a Trade Secret under applicable law.

## ARTICLE 19 – TERMINATION

Automatic termination. Your rights under this License terminate automatically without notice if you violate this License.

Effect of termination. Upon termination, you must:

Immediately stop using, copying, modifying, distributing, hosting, or operating the Software.

Destroy or return all copies of the Software in your possession or control within thirty (30) days, except to the extent retention is required by law.

Certify in writing to Shaleio that you have complied with Subsections (a) and (b) of this Section.

Survival. Sections intended by their nature to survive termination survive, including Articles 2, 3 (Section 4), 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, and 24.

Reinstatement. Shaleio may reinstate your rights in writing at its discretion. Reinstatement is not automatic and does not waive Shaleio’s right to pursue remedies for prior breaches.

Audit rights survival. Shaleio’s audit rights under Article 15 survive for three (3) years after termination for uses and activities that occurred during the term.

## ARTICLE 20 – DISCLAIMER OF WARRANTY

“AS IS” provision. THE SOFTWARE IS PROVIDED “AS IS,” “AS AVAILABLE,” AND WITHOUT WARRANTIES OF ANY KIND. TO THE MAXIMUM EXTENT PERMITTED BY LAW, SHALEIO DISCLAIMS ALL WARRANTIES, EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, NON-INFRINGEMENT, QUIET ENJOYMENT, SECURITY, AVAILABILITY, ACCURACY, RELIABILITY, AND ERROR-FREE OPERATION.

No operational warranties. SHALEIO DOES NOT WARRANT THAT THE SOFTWARE WILL:

Meet your requirements.

Operate without interruption.

Be secure or free from vulnerabilities.

Be error-free.

Prevent data loss, corruption, or unauthorized access.

Prevent unexpected cloud costs or resource consumption.

Be suitable for any particular production, regulated, government, defense, medical, financial, safety-critical, or mission-critical use.

Acknowledgment. You acknowledge that you use the Software at your own risk and that the Software is provided without any warranty or support commitment.

## ARTICLE 21 – LIMITATION OF LIABILITY

Exclusion of indirect damages. TO THE MAXIMUM EXTENT PERMITTED BY LAW, SHALEIO WILL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, PUNITIVE, OR ENHANCED DAMAGES, INCLUDING:

Lost profits, lost revenue, lost savings, or lost business opportunity.

Business interruption or loss of use.

Loss of goodwill or reputation.

Loss of data or cost of substitute data.

Security incidents, data breaches, or privacy violations.

Service interruption or degradation.

Cloud cost overruns, unexpected infrastructure charges, or resource consumption.

Your data; and

Procurement of substitute goods or services.

Aggregate liability cap. TO THE MAXIMUM EXTENT PERMITTED BY LAW, SHALEIO’S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATING TO THIS LICENSE OR THE SOFTWARE WILL NOT EXCEED ONE HUNDRED U.S. DOLLARS ($100).

Application of limitations. The limitations in Sections 1 and 2 of this Article apply:

Regardless of the legal theory or basis of the claim, including breach of contract, breach of warranty, tort, negligence, strict liability, misrepresentation, or any other theory.

Even if a remedy fails of its essential purpose or is found to have been insufficient.

Even if Shaleio has been advised of the possibility of such damages.

To the maximum extent permitted by applicable law.

Exceptions to limitation. The liability limitations in this Article do not limit:

Your obligations to pay commercial license fees for unlicensed use identified through audit under Article 15.

Your indemnity obligations under Article 22.

Your liability for breach of confidentiality obligations under Article 18 with respect to Trade Secrets or source code.

Your liability for violation of Shaleio’s intellectual property rights.

Liabilities that cannot be limited under applicable law.

## ARTICLE 22 – INDEMNITY

Your indemnity obligation. You agree to defend, indemnify, and hold harmless Shaleio and its owners, officers, employees, contractors, contributors, and agents from and against any and all third-party claims, demands, actions, damages, liabilities, losses, costs, and expenses, including reasonable attorneys’ fees, arising from or relating to:

Your use of the Software.

Your modifications to the Software.

Your Modules.

Your distribution of the Software.

Your violation of this License.

Your violation of applicable law, regulation, or third-party rights.

Your data, credentials, prompts, outputs, infrastructure, cloud environment, or systems.

Your products, services, customers, or end users.

Indemnification procedures. Your indemnification obligations under this Article are subject to the following conditions:

Shaleio will promptly notify you in writing of the claim, provided that delay in notification will not relieve you of your obligations except to the extent you are materially prejudiced by the delay.

You will have sole control of the defense and settlement of the claim, provided you may not settle any claim in a manner that imposes liability or non-monetary obligations on Shaleio without Shaleio’s prior written consent.

Shaleio will provide reasonable cooperation and assistance in the defense of the claim, at your expense for reasonable out-of-pocket costs.

Shaleio may participate in the defense with counsel of its own choice and at its own expense.

Third-party claims only. The indemnity obligation in this Article applies only to third-party claims and does not apply to disputes solely between you and Shaleio.

## ARTICLE 23 – INJUNCTIVE RELIEF

Acknowledgment of harm. You acknowledge that violation of Article 5 (Restrictions), Article 8 (Distribution of Modified Versions), Article 9 (Contributions), Article 10 (Attribution and Trademarks), or Article 18 (Confidentiality and Trade Secrets) may cause irreparable harm to Shaleio for which monetary damages may be inadequate.

Equitable remedies. Shaleio may seek injunctive relief, specific performance, or other equitable remedies to prevent or remedy such breach, without the need to post a bond or prove actual damages, in addition to any other remedies available at law or in equity.

## ARTICLE 24 – FORCE MAJEURE

Excused performance. Neither party will be liable for any delay or failure to perform its obligations under this License (other than payment obligations) to the extent such delay or failure is caused by events or circumstances beyond the affected party’s reasonable control, including acts of God, natural disasters, war, terrorism, civil unrest, labor disputes, strikes, internet or telecommunications failures, cloud provider failures or outages, government actions, epidemics, pandemics, or other widespread outages (“Force Majeure Event”).

License compliance not excused. Your obligation to comply with field-of-use restrictions, deployment restrictions, Enterprise Feature restrictions, intellectual property restrictions, confidentiality obligations, and other provisions of this License is not excused by Force Majeure to the extent reasonably practicable.

Termination for extended Force Majeure. If a Force Majeure Event continues for more than ninety (90) days and materially impairs a party’s ability to use or provide the Software, either party may terminate this License upon written notice to the other party.

## ARTICLE 25 – GOVERNING LAW, VENUE, AND DISPUTE RESOLUTION

Governing law. This License is governed by and construed in accordance with the laws of the State of Florida, United States, without regard to its conflict-of-law principles.

Exclusive venue. Except as provided in Section 3 of this Article, any legal action, suit, or proceeding arising out of or relating to this License must be brought exclusively in the state or federal courts located in Orange County, Florida. Each party irrevocably consents to the personal jurisdiction and venue of such courts and waives any objection to venue or inconvenient forum.

Equitable relief and IP enforcement. Notwithstanding Section 2 of this Article, Shaleio may seek injunctive relief, specific performance, or other equitable remedies, or may bring an action for intellectual property infringement, misappropriation of Trade Secrets, or breach of confidentiality, in any court of competent jurisdiction where your actions giving rise to the claim occurred or where your assets are located.

Attorney’s fees. In any legal action or proceeding arising out of or relating to this License, the substantially prevailing party will be entitled to recover its reasonable attorneys’ fees, expert witness fees, costs of investigation, and other litigation costs and expenses from the non-prevailing party, in addition to any other relief to which the prevailing party may be entitled.

## ARTICLE 26 – GENERAL TERMS

Entire agreement. This License is the entire agreement between you and Shaleio regarding the Software distributed under this License.

Severability. If any provision of this License is held invalid, illegal, or unenforceable by a court of competent jurisdiction, the remaining provisions remain in full force and effect, and the invalid provision will be modified to the minimum extent necessary to make it valid and enforceable while preserving the parties’ original intent. If such modification is not possible, the invalid provision will be severed and the remaining provisions will continue in effect.

No waiver. Failure to enforce any provision is not a waiver of that provision or of the right to enforce it in the future. A waiver of any breach or default will not constitute a waiver of any subsequent breach or default.

Assignment. You may not assign this License without Shaleio’s prior written consent. Any attempted assignment in violation of this Section is void. Shaleio may assign this License in connection with a merger, acquisition, reorganization, sale of assets, or transfer of the Software without restriction.

Updates to License. Shaleio may publish updated versions of this License for future versions of the Software. Your use of a specific version of the Software is governed by the license terms that accompanied that version unless you choose to use a later version under later terms.

Order of precedence. If you have a separate signed commercial agreement with Shaleio, that signed agreement controls to the extent it conflicts with this License.

Independent contractors. The parties are independent contractors. This License does not create a partnership, joint venture, agency, fiduciary relationship, employment relationship, franchise, or exclusive relationship between the parties. You have no authority to bind Shaleio or make commitments on its behalf.

No third-party beneficiaries. This License is for the sole benefit of the parties and their permitted successors and assigns. Nothing in this License, express or implied, is intended to or will confer upon any other person or entity any legal or equitable right, benefit, or remedy of any nature whatsoever. Indemnified persons under Article 22 are not intended to have independent enforcement rights unless expressly granted by separate written agreement.

Interpretation. In interpreting this License:

Headings and captions are for convenience only and do not affect interpretation.

“Including” means “including but not limited to.”

“Or” is not exclusive.

“Will” and “shall” are mandatory and “may” is permissive.

The singular includes the plural and vice versa.

References to Articles and Sections are to articles and sections of this License unless otherwise specified.

Notices. All notices required or permitted under this License must be in writing and will be deemed given when sent by confirmed electronic mail to the address provided below or when delivered personally or by confirmed courier service. Notices to Shaleio must be sent to: info@shaleio.com.

Language. This License is drafted in the English language. In the event any translation of this License is prepared, the English version will control in the event of any conflict or inconsistency.

## ARTICLE 27 – INSURANCE

No insurance requirement. Shaleio does not undertake to carry specific insurance for community users under this License. Each party is responsible for maintaining insurance appropriate to its own risk profile and use of the Software.

Commercial license insurance. For customers migrating to commercial licenses, Shaleio reserves the right to require insurance as specified in those separate commercial agreements.

## ARTICLE 28 – ACCEPTANCE

Acceptance. By using, copying, modifying, distributing, or deploying the Software, you agree to be bound by the terms and conditions of this License.

Authority. If you are accepting this License on behalf of an organization, you represent that you have the authority to bind that organization to the terms of this License.
