# Perform before the migration plan

Before permitting the migration plan, we need to perform the following steps:

1. rename the repo and project, plan, instructions, and other files to `workflow-orchestration-service` and `workflow-orchestration-client` to reflect the new structure and purpose of the two components. This will help avoid confusion and ensure that the names accurately represent the functionality of each component. The repo used to be named `workflow-orchetration-queue-tango48`. I have already renamed the repo and vs code workspace file. Any other references, and the plan files should be updated to reflect the new names.

2. the `project-setup` dynamic workflow orchestration and the the consituent workflow assignments have not been performed yet. Instead of performing them normally, you need to systemaaically analyze them all and gather a list of actions that they would have been performed and then perform those actions manually. Analyze the dynamic workflow and assignments an dcreate a plan in a markdown file to manually apply all changes that would have been applied by the dynamic workflow and assignments. Some of the items may have already been performed, or are not needed anymore.

3. Updates aplied to the `intel-agency/ai-newworkflow-app-template` repo recently, after this repo wa screated needed to found and appliued to this repo. Determine when and/or which revision of that repo was used to clone this repo from, and apply all cnages form commits after that to thhis repo. After analyaing, create a report markdown file with the commits that need to be applied and the actions that need to be performed to apply those commits.

After you present the reports for my approval, I will review them and provide feedback or approval to proceed with the manual application of the changes. Once approved, you can start implementing the necessary changes based on the reports you created. Make sure to document any changes you make and keep track of the progress. If you encounter any issues or have questions during the process, feel free to reach out for assistance.
