# Migration Task: Orchestration of OpenCode DevContainer Server Standalone Self-Hosted Service Plans

## Overview
This document outlines the tasks and plans for migrating the orchestration workflow agent to a standalone service that runs the orchestration entirely from within the Docker and DevContainer service. The goal is to enhance the modularity, scalability, and maintainability of the orchestration system. 

The key idea is take all of the current files, from the workspace root and add COPY commands in the Dockerfile to include them in the final image, so they are are completely self-conained in the Dockerfile. The devontainer image will be built with Docker image as its base image and prebuilt using the same patterna and exisitng system are and have been using (and exists in this repo, as well as the `intel-agency/workflow-orchestration-prebuild` repo), and also for the current `intel-agency/workflow-orchestration-queue` agent.

This migration aims to decouple the orchestration workflow agent from its current tightly integrated environment and re-establish it as a self-contained, self-hosted service. This will allow for more flexible deployment options, easier updates, and improved resource management.

## Key Considerations

### Event Delivery Interface

The only remaining issue is to decide on the interface for delviering the triggered (e.g. GitHub) events and their payloads to the orchestration workflow agent. This will be a critical aspect of the migration, as it will determine how the agent receives and processes events in its new standalone environment. Possible options include, but are not limied to using:

- a message queue
- a REST API
- a webhook-based approach

>The webhook approach is the best option for this migration, as it is already being used by the GitHub webhook service, and it is a well-established pattern for event-driven architectures.

### Prompting the Server
The other remaining and entanlged issue, is how the webhook/interface will prompt the running orchestration agent service. 

Options include:

1. having the webhook handler url actually _inside_ the orchestration agent service, so that the webhook directly triggers the agent, or 
2. having a separate webhook handler service that receives the events and then forwards them to the orchestration agent service. The latter approach would add an additional layer of indirection, but it could also provide more flexibility and separation of concerns. in this case the webhook handler would have its own copy of the `devcontainer_opencode.sh` script and the server's address and port, which it would use to call the `devcontainer_opencode.sh` script with the `prompt -p "Received event: $event_payload"` command to trigger the orchestration agent service.

>I am currently favoring option 2. This would allow for better separation of concerns, as the webhook handler would be responsible for receiving and processing events, while the orchestration agent service would focus on executing the workflow logic. Additionally, this approach would make it easier to scale the webhook handler independently of the orchestration agent service, if needed. 

## Current State of the Repo

I have created a cloned instance of the `intel-agency/ai-new-workflow-app-template` template repo, which is the current implementation of the orchestration workflow agent that we familair with. 

I then copied the files from `intel-agency/workflow-orchestration-prebuild` repo into this repo, adding in all of the changes from there. This is the first step towards migrating the `intel-agency/ai-new-workflow-app-template` template repo cloned instance to a standalone service.

There are some outstanding changes that still need to be kept or reverted. You will see them as uncommiited chnages in this current repo.

After we make some moe changes in this repo I will eventally cvhange the repo name and path to `intel-agency/workflow-orchestration-service`.

## Architecture

We will have a networked client/server architecture. 
- The server will be a standalone service that runs the orchestration workflow agent. 
  - The server will contain the orchestration agent workfow and cae macthing prompt exaactly as before (it will reiuse the existing files and logic)

- The client will be a  python script that contains a webhook handler thant will call the prompt script with the remote server address and port to invoke orchestration workfows on the server when events are received. (The client will also have the `devcontainer_opencode.sh` script, which it will use to call the server usning the `prompt -p "Received event: $event_payload"` command to trigger the orchestration agent service.)
  

## Next Steps

1. Decide on the outstanding changes to keep or revert.
2. Review the current state of this rpeo after I combined the two, and make any necessary changes to the code to ensure it works as expected.
3. Implement the migration of the orchestration workflow agent to a standalone service. This will involve:

We will focus on the following task first:

   1. Updating the Dockerfile to include all necessary files and dependencies for the standalone service. You should basically only need to add COPY statements for all the files at the workspace root, and then correct the paths and any logic that needs to be updated to reflect the new structure of the service.
   - Testing the standalone service to ensure it functions correctly (starts and runs and exits and can run the service and orchestrate weorklfows when prompted. We will reuse the `devcontainer_opencode.sh` script to ensure it can be called from the remote client and correctly orchestrate workflows.
   
   - We can use canned testing prompts (some exist) for the validation.

   *<AC and validaiton steps here>*

   2. After that we can work on the remote client's prompt script command and sessions started remotely.

   *<AC and validaiton steps here>*

   3. Finally we can implement the webhook hanlder part of the remote client which will receive events and call the prompt script (from part 2. above)with the remote server address and port to invoke orchestration workfows on the server when events are received.

   *<AC and validaiton steps here>*

     - The initial event source will be a GitHub app that recveives the samne events we have been using and calls webhooks to the webhook handler in the remote client.

     *<AC and validaiton steps here>*


**Note**: The migration process will be iterative, and we need to have c;lear AC and validation plans ar each stage. I will not consider trhe step complete until you can deomonstrate the validaiton steps and AC are succesfully met.

## Exisitng Code

All of the existing code is in this repo and should be used as the basis for the migration. This includes the Dockerfile, the `devcontainer_opencode.sh` script, and all of the files at the workspace root that are currently used by the orchestration workflow agent. COPY them into the DOckerfile and update any paths and logics and other refewrences as needed to reflect the new structure of the service.

Specifically, tthere are python files that exist for the webhook handler and data model in this repo:

- <plan_docs\notifier_service.py>
- <plan_docs\orchestrator_sentinel.py>
- <scripts\WorkItemModel.py>


## Plan docs

- <docs\extra-repo-orchestration-opencode-devcontainer-server-standalone-self-hosted-service_plans\F1-feature-full-dev-plan.md>
- <docs\extra-repo-orchestration-opencode-devcontainer-server-standalone-self-hosted-service_plans\F1-orchestration-migration-options.md>
- <docs\extra-repo-orchestration-opencode-devcontainer-server-standalone-self-hosted-service_plans\F1-full-dev-plan_(OPENCODE).md>

- <plan_docs/*.md>


