# Sample project

A tiny project used as dochealer's test fixture.

## Usage

Call `get_user()` with a user ID. Pass `include_inactive=True` to also fetch
deactivated accounts. Users can be removed with `delete_user()`.

## Configuration

### Retries

The `Settings` class controls retry behavior. `retry_delay` defaults to **5 seconds**
and `max_retries` defaults to **3**. Call `reload()` to re-read the environment.

### Timeouts

Requests use `DEFAULT_TIMEOUT`, which defaults to **30 seconds**.

## Unrelated section

This section talks about the project license and mentions no code at all.
