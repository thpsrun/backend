### v4.1.0
###### June 2, 2026
*   Added
    *   Added a new query option to `/players/search?` that allows you to search for specific Twitch names.
    *   Added a new `/{id}/import-issues` endpoint that allows mods to see what invalidation were raised when the run was imported from SRC.
    *   Added additional logic to remove speedruns that were deleted from SRC.
    *   Added additional checks to Celery tasks so it doesn't re-iterate the same runs over and over and over and over and over and over and over and over and over and over and over and over...

*   Fixed
    *   Fixed an issue where uploading runs from thps.run would fail when converting DateTimeFields.
    *   Fixed an issue where `vid_status` was missing from POST `/runs`
    *   Fixed an issue where POST `/runs` did not ingest `*_secs` and self-create the human-friendly form of times.
    *   Fixed an issue where Celery tasks, in some situations, would call the wrong world record from the wrong category, calculate off of that, and report a point total that was insanely high (one example had a run get 408 MILLION HOLY).
    *   Fixed an issue where PUT'ing variables to `/runs` would cause issues with validation if the run was a legacy run.

### v4 - The Definitive Update
###### June 1, 2026

### Major Changes

#### Overall
*   Entire frontend of the website is redesigned. New UI, not basic HTML/JS, and much more!!? This is all hosted on the frontend repo, just to keep Django's complexities separate from React's. (Thanks to Noami for helping get started! <3)
    *   New main page!
    *   New game screen!
    *   New login system!
        *   SRC API Key is required to integrate!
    *   New game pages!
        *   Full-game and ILs have new views!
    *   New rankings!
    *   New player profile pages!?
*   Introducing `Run History`!
    *   Runs have been crawled from the beginning of the community's history to current day to help determine rankings, points, and records throughout history!
    *   Ranking pages now go back to over a decade ago to show the progress of the Overall rankings by year or month, and can be done by game!
*   Migrated the entire API to Django Ninja.
    *   Versioned the API endpoints for future-proofing and to allow better API upgrading as new features/endpoints are added/tested.
    *   GET endpoints are now publicly accessible! All other methods will require authentication.
        *   API Keys can be created by authenticated users, with regular users getting vast GET permissions, moderators getting more, and super admins getting even more.
    *   Documentation is also publicly accessible via `/api/v1/docs`.
*   Rebuilt the Guides system to be within the API instead of GitHub.
    *   Guides are now easily shown on the game's page, and from there you can create new guides with tags!
*   Consolidated the SRC -> thps.run pipeline from two different chains into one.
*   Caching has been added to all API endpoints.
    *   Cached responses last ~7 days.
        *   Upon a run, category, or player account being updated, then this will also update the cached.
*   Categories, Levels, and Variable:Value pairs can now be individually re-ordered dynamically via new Django Action panels.

#### Points
*   Points Algorithm Adjustments!
    *   **If an IL is under 60 seconds, then a different algorithm is used to reduce decay.**
    *   Current Formula: `P = e^(4.8284 * (WR/PB - 1)) * max_points`
    *   New Formula: `P = e^(4.8284 * √(WR/60) * (WR/PB - 1)) * max_points`
    *   10 Second IL Example:
        *   `P = e^(4.8284 * √(10/60) * (10/X - 1)) * 100`
  
        | **Placement** | **Time (RTA)** | **Old Algorithm** | **New Algorithm** | **Differential** |
        |---------------|----------------|-------------------|-------------------|------------------|
        | 1             | 0:10           | 100               | 100               |      **--**      |
        | 2             | 0:11           | 64                | 83                |      **+19**     |
        | 3             | 0:12           | 44                | 71                |      **+27**     |
        | 4             | 0:15           | 19                | 51                |      **+32**     |
        | 5             | 0:17           | 13                | 44                |      **+31**     |
        | 6             | 0:20           | 8                 | 37                |      **+29**     |
    *   30 Second IL Example:
        *   `P = e^(4.8284 * √(30/60) * (30/X - 1)) * 100`

        | **Placement** | **Time (RTA)** | **Old Algorithm** | **New Algorithm** | **Differential** |
        |---------------|----------------|-------------------|-------------------|------------------|
        | 1             | 0:30           | 100               | 100               |      **+0**      |
        | 2             | 0:31           | 85                | 89                |      **+4**      |
        | 3             | 0:34           | 56                | 66                |      **+10**     |
        | 4             | 0:44           | 21                | 33                |      **+12**     |
        | 5             | 0:50           | 14                | 25                |      **+11**     |
        | 6             | 1:00           | 8                 | 18                |      **+10**     |
    >[!NOTE]
    > Yeah, it isn't a HUGE difference, and in some cases it can be scaled weirdly, but the idea is to reign in the crazy curve the shorter ILs cause. Obvious examples are the THPS1 competition ILs, since they are super quick and go by IGT. But, because of that, the point differential is a lot crazier there than it is versus longer runs.
    >
    > Is it a perfect system? No. But, I am always up for suggestions since I am NOT a math geek. 
*   Points Evaluation Adjustments!
    *   ILs now give a maximum of 250 points.
        *   The example above used the old system for simplicity.
    *   CEs now give a maximum of 50 points.
*   New Point Streaks System!
    *   Bonus points awarded to world record holders to incentivize optimization.
        *   It is player-based; meaning, if you beat your own world record, the streak stays! If someone beats you at any point, the streak is broken.
    *   Awarded on the month anniversary of the player gaining the record.
        *   Full Game Runs: WR holders will receive an extra 125 points each month for a maximum of 4 months (1000 for WR + 500 for streak max).
        *   IL Runs: WR holders will receive an extra 31.25 points each month for a maximum of 4 months (250 for WR + 125 for streak max).
        *   CE Runs: Unaffected by Streaks.


### Added
*   Added a brand new login system that requires a valid SRC API Key to determine if you own your account.
    *   Runners without an `approved` run will not be able to make an account until it is approved.
    *   Runners can elect to keep their SRC API Key saved in the database or not. If you do, you can submit runs through the site!
        *   API Keys are encrypted in transit and at rest.
*   Added the ability for runners to sign-up with Discord and Twitch, allowing for passwordless setups!
    *   SRC API Key is still required!
*   Added the ability to use a passkey as a method to log into the site.
*   Added the ability to remove passwords, passkeys, and OAuth methods - as long as one valid form remains at all times.
*   Added indexes to multiple models to help speed up load times in virtually all instances.
*   Added `appear_on_main` field to `Categories` and `VariableValues` that will allow for querying only categories that, well, we only want to appear on the main page.
    *   Also added a devoted page to the superuser's `Admin Panel` to help decide which runs appear on the front page.
*   Added the ability for superadmins to adjust the ordering of `Categories`, `Variable-Value` pairs, and `Levels`.
*   Added `order` field to `Categories`, `Levels`, and `VariableValues` that will help establish the order of that model when returned from the API.
    *   Also created a specialized `Manage Category & Level Ordering` Django Action to help admins manage the order of the model objects.
*   Added a new `is_ce` property to `Games` to help centralize determining if the object is a Category Extension or not.
*   Added `archived` field to `Variables`, `VariableValues`, `Categories`, and `Levels`.
*   Added `rules` field to  `Variables`, `VariableValues`, `Categories`, `Levels` and `Games`.
*   Added the ability to see rules in submit and edit run views and on the category's page.
*   Added a `Categories`-specific override that lets you force change the default timing method of the category.
    *   THPS4 5th Gen, you're welcome.
*   Added `slug` field to `Variables`, `VariableValues`, `Categories`, `Levels` and `Platforms`.
*   Added a new `/website` endpoint that is more catered to interacting with React.
*   Added Pydantic schema and models.
    *   About time tbh.
*   Added "smart" caches that are generated and stored for 7 days unless data is modified.
    *   This was mostly meant for the React endpoints, but has been extended to all endpoints to keep them consistent.
    *   Logic has been added to help invalidate caches when data is updated.
*   Added new tests and vulnerability checks to the project's CI/CD pipeline to catch problems before they are pushed to production.
*   Added a new Dockerfile build process to reduce the size of the overall images and harden it for regulatory compliance.
*   Added the ability for runners to delete themselves from the database.
    *   Their run data will remain, but will be marked as `Anonymous`.
*   Added the ability for runners to backup their data to a .zip format.

> There is definitely a lot more I forgot to add! But, yeah, a lot has changed <3

### Fixed
*   Fixed all sorts of type checking issues throughout the project.
*   Fixed the logic calculating a run's `points` and `place` fields so they are more consistent.
*   Fixed an issue where the PostgreSQL database would revert database changes upon a restart.
*   Fixed an issue where the returned API request from POST or PUT would (most times) fail to provide a proper response due to a race condition.
*   Fixed an issue where development servers would fail to serve CSS and Static files on refresh.
*   Fixed an issue where the Django image would be caught in an infinite loop if Celery tasks weren't properly ended.
    *   Celery tasks are a separate image now, still integrated with Django.

### Changed
*   Changed the Guides system so it can be accessible via the Django Admin interface (for super admins of the project), the API via GET request, and the new portal.
*   Changed the API key system so that it will be scoped based on role. Each role has different rate limits (with admins having unlimited).
*   Changed the ordering of levels and category names so they reflect better what is seen on Speedrun.com.
    *   This is mostly hard-coded. Ordering on SRC is done on server-side, so there is no way around that besides either having a "ranking" system or just hard-coding what the order should be. (Sue me).
*   Changed the API so it is separated into "general"/"standard" and "website" API requests.
    *   React will be using a lot of the thps.run API, so separating this will help keep features separate and also allow us to do fancier things.
*   Changed the `/player` endpoint to both return no stats on default and to require the `?embed=stats` request to add stats to the query.
    *   When interacting with larger sets of data, especially when stats aren't required, it can cause slow down.
*   Changed `hidden` to `archive` within `Variables`, `VariableValues`, and `Categories`.
    *   `Archive` will mimic what you see from archived variables or categories. They are excluded from searches, as well, but will help ensure runs do not get orphaned.
    *   SRC's v1 API does not expose this, so it must be done manually (we don't have many that have this anyways).
*   Changed the amount of characters in the `Rules` field of `Categories`, `Variables`, and `VariableValue` to 5,000 (up from 1,000).

### Removed
*   Removed `all_cats` as a field, since new logic helps consolidate field options.
*   Removed `subcategory` from all `Runs` objects.
    *   There is now a dynamic process to show the full subcategory instead of it needing to be updated everytime a category and/or variable is to be updated.