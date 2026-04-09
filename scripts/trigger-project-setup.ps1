#!/usr/bin/env pwsh

<#
.SYNOPSIS
    Trigger the project-setup dynamic workflow for a repository.

.DESCRIPTION
    Convenience wrapper around create-dispatch-issue.ps1 for the legacy
    project-setup entrypoint. Supports dry-run output for validation and
    forwards optional metadata to the issue creation command.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^/]+/[^/]+$')]
    [string]$Repo,

    [Parameter()]
    [string]$Project,

    [Parameter()]
    [string]$Milestone,

    [Parameter()]
    [string]$Template,

    [Parameter()]
    [string[]]$Assignee,

    [switch]$DryRun
)

$dispatchScript = Join-Path $PSScriptRoot 'create-dispatch-issue.ps1'
if (-not (Test-Path -LiteralPath $dispatchScript)) {
    throw "Required helper script not found: $dispatchScript"
}

$body = @'
/orchestrate-dynamic-workflow
$workflow_name = project-setup
'@

Write-Host 'Project setup dispatch details:' -ForegroundColor Cyan
Write-Host "  Repo:      $Repo"
Write-Host '  Workflow:  project-setup'
if ($Project) { Write-Host "  Project:   $Project" }
if ($Milestone) { Write-Host "  Milestone: $Milestone" }
if ($Template) { Write-Host "  Template:  $Template" }
if ($Assignee) { Write-Host "  Assignee:  $($Assignee -join ', ')" }

if ($DryRun) {
    Write-Host '[dry-run] Would create a dispatch issue for project-setup.' -ForegroundColor Yellow
    exit 0
}

$invokeArgs = @{
    Repo = $Repo
    Body = $body
}

if ($Project) { $invokeArgs.Project = $Project }
if ($Milestone) { $invokeArgs.Milestone = $Milestone }
if ($Template) { $invokeArgs.Template = $Template }
if ($Assignee) { $invokeArgs.Assignee = $Assignee }

& $dispatchScript @invokeArgs
exit $LASTEXITCODE
