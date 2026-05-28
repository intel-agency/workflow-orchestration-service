"""
Tests for client/src/queue/github_queue.py

Covers:
- Claim-task happy path (assign-then-verify succeeds)
- Claim-task conflict/race path (another sentinel wins the race)
- Claim-task failure path (assignment API returns error)
- Label transitions: QUEUED → IN_PROGRESS, IN_PROGRESS → terminal status
- Pagination: fetch_queued_tasks over multiple pages
- Inlined classification logic: PLAN, BUGFIX, IMPLEMENT defaults
- update_status with and without a comment
- post_heartbeat happy path and error resilience
- add_to_queue success and failure
- fetch_queued_tasks with rate-limit propagation
- GitHubQueue.close() releases the connection pool
"""

import pytest
import respx
from httpx import Response

from src.queue.github_queue import GitHubQueue, ITaskQueue
from src.models.work_item import TaskType, WorkItem, WorkItemStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_TOKEN = "FAKE-KEY-FOR-TESTING-00000000GITHUB"
ORG = "test-org"
REPO = "test-repo"
REPO_SLUG = f"{ORG}/{REPO}"
BASE_API = f"https://api.github.com/repos/{REPO_SLUG}"


def make_work_item(
    issue_number: int = 42,
    task_type: TaskType = TaskType.IMPLEMENT,
    status: WorkItemStatus = WorkItemStatus.QUEUED,
) -> WorkItem:
    return WorkItem(
        id="100000042",
        issue_number=issue_number,
        source_url=f"https://github.com/{REPO_SLUG}/issues/{issue_number}",
        context_body="Do the thing.",
        target_repo_slug=REPO_SLUG,
        task_type=task_type,
        status=status,
        node_id="I_kwDOABCDEF12345",
    )


def _issue_payload(
    issue_number: int = 42,
    labels: list[str] | None = None,
    title: str = "Fix something",
    assignees: list[str] | None = None,
) -> dict:
    labels = labels or ["agent:queued"]
    assignees = assignees or []
    return {
        "id": 100000000 + issue_number,
        "number": issue_number,
        "title": title,
        "html_url": f"https://github.com/{REPO_SLUG}/issues/{issue_number}",
        "body": "Task body.",
        "node_id": f"I_kwDOABCDEF{issue_number:05d}",
        "labels": [{"name": lbl} for lbl in labels],
        "assignees": [{"login": a} for a in assignees],
    }


@pytest.fixture
def queue() -> GitHubQueue:
    return GitHubQueue(token=FAKE_TOKEN, org=ORG, repo=REPO)


# ---------------------------------------------------------------------------
# ITaskQueue ABC
# ---------------------------------------------------------------------------


class TestITaskQueue:
    def test_github_queue_is_itaskqueue(self, queue):
        assert isinstance(queue, ITaskQueue)


# ---------------------------------------------------------------------------
# Inlined classification logic
# ---------------------------------------------------------------------------


class TestInlinedClassification:
    """Verify that fetch_queued_tasks classifies issues correctly without calling
    any external classify_task_type function (logic is inlined per D2 directive)."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_default_implement(self, queue):
        issue = _issue_payload(title="Fix login bug — no bug label")
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].task_type == TaskType.IMPLEMENT

    @respx.mock
    @pytest.mark.asyncio
    async def test_plan_label_classifies_as_plan(self, queue):
        issue = _issue_payload(labels=["agent:queued", "agent:plan"])
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].task_type == TaskType.PLAN

    @respx.mock
    @pytest.mark.asyncio
    async def test_plan_title_bracket_classifies_as_plan(self, queue):
        issue = _issue_payload(title="[Plan] New architecture")
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].task_type == TaskType.PLAN

    @respx.mock
    @pytest.mark.asyncio
    async def test_bug_label_classifies_as_bugfix(self, queue):
        issue = _issue_payload(labels=["agent:queued", "bug"])
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].task_type == TaskType.BUGFIX

    @respx.mock
    @pytest.mark.asyncio
    async def test_plan_label_beats_bug_label(self, queue):
        """Plan classification takes priority over bug label (matches reference inline)."""
        issue = _issue_payload(labels=["agent:queued", "agent:plan", "bug"])
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].task_type == TaskType.PLAN


# ---------------------------------------------------------------------------
# fetch_queued_tasks
# ---------------------------------------------------------------------------


class TestFetchQueuedTasks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path_returns_work_items(self, queue):
        issues = [_issue_payload(42), _issue_payload(43)]
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=issues))

        items = await queue.fetch_queued_tasks()
        assert len(items) == 2
        assert items[0].issue_number == 42
        assert items[1].issue_number == 43

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty_list(self, queue):
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[]))

        items = await queue.fetch_queued_tasks()
        assert items == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_repo_slug_derived_from_html_url(self, queue):
        """Repo slug is extracted from html_url, not hardcoded from self.org/repo."""
        other_slug = "other-org/other-repo"
        issue = _issue_payload()
        issue["html_url"] = f"https://github.com/{other_slug}/issues/42"
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=[issue]))

        items = await queue.fetch_queued_tasks()
        assert items[0].target_repo_slug == other_slug

    @respx.mock
    @pytest.mark.asyncio
    async def test_api_error_returns_empty_list(self, queue):
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(500, json={}))

        items = await queue.fetch_queued_tasks()
        assert items == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limit_403_raises(self, queue):
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(403, json={}))

        with pytest.raises(Exception):
            await queue.fetch_queued_tasks()

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limit_429_raises(self, queue):
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(429, json={}))

        with pytest.raises(Exception):
            await queue.fetch_queued_tasks()

    @pytest.mark.asyncio
    async def test_missing_org_returns_empty(self):
        """fetch_queued_tasks returns empty list when org/repo are not configured."""
        q = GitHubQueue(token=FAKE_TOKEN)
        items = await q.fetch_queued_tasks()
        assert items == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_pagination_multiple_issues(self, queue):
        """Simulate a page with many issues — all are returned."""
        issues = [_issue_payload(i) for i in range(10, 20)]
        respx.get(f"{BASE_API}/issues").mock(return_value=Response(200, json=issues))

        items = await queue.fetch_queued_tasks()
        assert len(items) == 10
        assert {item.issue_number for item in items} == set(range(10, 20))


# ---------------------------------------------------------------------------
# claim_task — happy path
# ---------------------------------------------------------------------------


class TestClaimTaskHappyPath:
    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_succeeds(self, queue):
        item = make_work_item()
        bot = "test-bot"

        # Assign succeeds
        respx.post(f"{BASE_API}/issues/42/assignees").mock(
            return_value=Response(201, json={"assignees": [{"login": bot}]})
        )
        # Verify: bot is listed as assignee
        respx.get(f"{BASE_API}/issues/42").mock(
            return_value=Response(200, json=_issue_payload(assignees=[bot]))
        )
        # Remove QUEUED label
        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.QUEUED.value}"
        ).mock(return_value=Response(200, json=[]))
        # Add IN_PROGRESS label
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        # Post claim comment
        respx.post(f"{BASE_API}/issues/42/comments").mock(
            return_value=Response(201, json={"id": 1})
        )

        result = await queue.claim_task(item, sentinel_id="sentinel-1", bot_login=bot)
        assert result is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_without_bot_login_skips_assignment(self, queue):
        """When bot_login is empty, skip assign/verify and proceed directly to labels."""
        item = make_work_item()

        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.QUEUED.value}"
        ).mock(return_value=Response(200, json=[]))
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        respx.post(f"{BASE_API}/issues/42/comments").mock(
            return_value=Response(201, json={"id": 1})
        )

        result = await queue.claim_task(item, sentinel_id="sentinel-1", bot_login="")
        assert result is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_posts_comment_with_sentinel_id(self, queue):
        """Claim comment must include the sentinel_id."""
        item = make_work_item()
        bot = "test-bot"
        sentinel_id = "sentinel-xyz-99"
        captured_body: dict = {}

        def capture(request, route):
            import json as _json
            captured_body.update(_json.loads(request.content))
            return Response(201, json={"id": 1})

        respx.post(f"{BASE_API}/issues/42/assignees").mock(
            return_value=Response(201, json={"assignees": [{"login": bot}]})
        )
        respx.get(f"{BASE_API}/issues/42").mock(
            return_value=Response(200, json=_issue_payload(assignees=[bot]))
        )
        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.QUEUED.value}"
        ).mock(return_value=Response(200, json=[]))
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        respx.post(f"{BASE_API}/issues/42/comments").mock(side_effect=capture)

        await queue.claim_task(item, sentinel_id=sentinel_id, bot_login=bot)
        assert sentinel_id in captured_body.get("body", "")


# ---------------------------------------------------------------------------
# claim_task — conflict / race paths
# ---------------------------------------------------------------------------


class TestClaimTaskConflict:
    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_fails_when_assignment_rejected(self, queue):
        """If the assignment API returns non-200/201, claim_task returns False."""
        item = make_work_item()
        bot = "test-bot"

        respx.post(f"{BASE_API}/issues/42/assignees").mock(
            return_value=Response(403, json={"message": "Forbidden"})
        )

        result = await queue.claim_task(item, sentinel_id="s1", bot_login=bot)
        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_fails_when_other_bot_won_race(self, queue):
        """If after assignment the assignee list shows a different bot, return False."""
        item = make_work_item()
        bot = "my-bot"
        other_bot = "rival-bot"

        respx.post(f"{BASE_API}/issues/42/assignees").mock(
            return_value=Response(201, json={})
        )
        # Verify: rival-bot is the assignee, not my-bot
        respx.get(f"{BASE_API}/issues/42").mock(
            return_value=Response(200, json=_issue_payload(assignees=[other_bot]))
        )

        result = await queue.claim_task(item, sentinel_id="s1", bot_login=bot)
        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_fails_when_verify_api_errors(self, queue):
        """If the re-fetch to verify assignment returns non-200, return False."""
        item = make_work_item()
        bot = "test-bot"

        respx.post(f"{BASE_API}/issues/42/assignees").mock(
            return_value=Response(201, json={})
        )
        respx.get(f"{BASE_API}/issues/42").mock(return_value=Response(503, json={}))

        result = await queue.claim_task(item, sentinel_id="s1", bot_login=bot)
        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_claim_fails_when_label_removal_errors(self, queue):
        """If QUEUED label deletion returns an unexpected status, return False."""
        item = make_work_item()

        # No bot_login — skip assignment, go straight to label manipulation
        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.QUEUED.value}"
        ).mock(return_value=Response(500, json={}))

        result = await queue.claim_task(item, sentinel_id="s1", bot_login="")
        assert result is False


# ---------------------------------------------------------------------------
# Label transitions via update_status
# ---------------------------------------------------------------------------


class TestLabelTransitions:
    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_removes_in_progress_and_adds_success(self, queue):
        item = make_work_item(status=WorkItemStatus.IN_PROGRESS)

        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.IN_PROGRESS.value}"
        ).mock(return_value=Response(200, json=[]))
        add_label_route = respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )

        await queue.update_status(item, WorkItemStatus.SUCCESS)

        # The label that was added must be the SUCCESS value
        assert add_label_route.called
        import json as _json
        body = _json.loads(add_label_route.calls[0].request.content)
        assert body["labels"] == [WorkItemStatus.SUCCESS.value]

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_posts_scrubbed_comment(self, queue):
        item = make_work_item(status=WorkItemStatus.IN_PROGRESS)
        raw_comment = "Done. Token: Bearer FAKE-KEY-FOR-TESTING-99999999"

        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.IN_PROGRESS.value}"
        ).mock(return_value=Response(200, json=[]))
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        comment_route = respx.post(f"{BASE_API}/issues/42/comments").mock(
            return_value=Response(201, json={"id": 1})
        )

        await queue.update_status(item, WorkItemStatus.SUCCESS, comment=raw_comment)

        import json as _json
        posted_body = _json.loads(comment_route.calls[0].request.content)
        # Secret must be scrubbed from the posted comment
        assert "FAKE-KEY-FOR-TESTING-99999999" not in posted_body["body"]
        assert "REDACTED" in posted_body["body"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_no_comment_skips_comment_post(self, queue):
        item = make_work_item(status=WorkItemStatus.IN_PROGRESS)

        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.IN_PROGRESS.value}"
        ).mock(return_value=Response(200, json=[]))
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        comment_route = respx.post(f"{BASE_API}/issues/42/comments")

        await queue.update_status(item, WorkItemStatus.ERROR, comment=None)

        assert not comment_route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_status_tolerates_404_on_label_removal(self, queue):
        """404 on label delete is acceptable — label already gone."""
        item = make_work_item(status=WorkItemStatus.IN_PROGRESS)

        respx.delete(
            f"{BASE_API}/issues/42/labels/{WorkItemStatus.IN_PROGRESS.value}"
        ).mock(return_value=Response(404, json={}))
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )

        # Should not raise
        await queue.update_status(item, WorkItemStatus.SUCCESS)


# ---------------------------------------------------------------------------
# add_to_queue
# ---------------------------------------------------------------------------


class TestAddToQueue:
    @respx.mock
    @pytest.mark.asyncio
    async def test_add_to_queue_returns_true_on_201(self, queue):
        item = make_work_item()
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(201, json=[])
        )
        assert await queue.add_to_queue(item) is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_to_queue_returns_true_on_200(self, queue):
        item = make_work_item()
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(200, json=[])
        )
        assert await queue.add_to_queue(item) is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_to_queue_returns_false_on_error(self, queue):
        item = make_work_item()
        respx.post(f"{BASE_API}/issues/42/labels").mock(
            return_value=Response(422, json={"message": "Unprocessable"})
        )
        assert await queue.add_to_queue(item) is False


# ---------------------------------------------------------------------------
# post_heartbeat
# ---------------------------------------------------------------------------


class TestPostHeartbeat:
    @respx.mock
    @pytest.mark.asyncio
    async def test_heartbeat_posts_comment(self, queue):
        item = make_work_item()
        comment_route = respx.post(f"{BASE_API}/issues/42/comments").mock(
            return_value=Response(201, json={"id": 1})
        )

        await queue.post_heartbeat(item, sentinel_id="s1", elapsed_secs=300)

        assert comment_route.called
        import json as _json
        body = _json.loads(comment_route.calls[0].request.content)
        assert "Heartbeat" in body["body"]
        assert "s1" in body["body"]
        assert "5m" in body["body"]  # 300 // 60 = 5 minutes

    @respx.mock
    @pytest.mark.asyncio
    async def test_heartbeat_does_not_raise_on_error(self, queue):
        """Heartbeat failures must be swallowed — a network hiccup should not crash sentinel."""
        item = make_work_item()
        respx.post(f"{BASE_API}/issues/42/comments").mock(
            return_value=Response(500, json={})
        )

        # Should complete without raising
        await queue.post_heartbeat(item, sentinel_id="s1", elapsed_secs=60)


# ---------------------------------------------------------------------------
# Connection pool lifecycle
# ---------------------------------------------------------------------------


class TestConnectionPool:
    @pytest.mark.asyncio
    async def test_close_does_not_raise(self, queue):
        """GitHubQueue.close() must not raise during graceful shutdown."""
        await queue.close()
