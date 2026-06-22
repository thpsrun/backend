# thps.run Website - Backend

### What the heck is this??
This has been the pet project of [Anastasia](https://twitch.tv/theanastasia) for a few years now. In short, it is a highly-customizable, easy-to-use, and curated website that aims to mimic a lot of the leaderboard functionality seen from [HaloRuns](https://haloruns.com). Built entirely in Django (Python), this is the open-source files used for websites like [thps.run](https://thps.run).  
  
This repo, specifically, is for the backend portion. If you wish to help with the frontend (React/TypeScript), then you can find it here: [thps.run Frontend](https://github.com/thpsrun/frontend).

### How does this work?
thps.run is essentially a 1:1 mirror of the Speedrun.com leaderboards for the [Tony Hawk's Pro Skater speedrun community](https://speedrun.com/tonyhawk). All runs are imported into custom models that mimic the layout and feel of Speedrun.com's API. From here, we are able to perform limitless lookups, customize experiences and create new features, and introduce fun stuff like the [Points System](#note-on-points).  
  
When you initially setup this project in your environment, you will need to import a `Series ID` into the `Series` model in the Admin Panel (easily gettable if you just take the series ID from any `https://speedrun.com/api/v1/series/<SERIES_SLUG>` request). While this means that ONLY communitys who have a Series for their game can use this project, it will allow you to have greater dynamic control of your community's speedruns.

### But why?
While SRC has improved a little bit over the last few years, every community should be free to create a decentralized leaderboard of some kind. Very large communities (like Megaman) already have their own websites, and this project serves as a way to quickly build one.
  
Will this work for everyone? No. Can you curate it to fit your community? Yes!

### Can I fork this project?
1.  This project assumes you are familar with Python and/or Django, with some sort of frontend to support it (note: you can use Django's built-in template system for a basis). A lot of processes and procedures are largely automated, but there may be some tweaks that you need to apply for your use case.
    *   Example: Currently, this project doesn't support speedruns with more than two players. If you support a community with more than 2, you will need to take this and curate things.
        *   Later versions will fix this.
    * Another example: THPS doesn't have any game with more than two sub-categories (variables), so you will need to customize things a bit.
        *   Later versions will also fix this.
2.  This project assumes you have permission to use the HaloRuns points system. [See below](#note-on-points).
3.  Contributing to this project is encouraged, but definitely not necessary. Commits to this project are **primarily** meant to enhance the thps.run experience or fix security problems. If you find something that can help, feel free to submit a PR!

### Requirements
* [Docker](https://www.docker.com/products/docker-desktop/) (Desktop or Docker Compose is fine)

### Note on Points
The points system utilized within this project was created by ibeechu and goatrope of the [HaloRuns](https://haloruns.com) speedrun community. For the use of thps.run, they are used with permission; if you wish to use this points system, then contact them on their official Discord for permission.

Points (lovingly referred to as Packle Points by the THPS community) is a score given to all speedruns. It incentivites players into trying out different speedruns or categories within the series.

This is how points are distributed when you have a world record:
*   Full-game (non-Category Extensions): 1000 points
*   Individual Levels: 250 points
*   Category Extensions: 50 points

Additionally, Streaks are bonus points awarded to players if they continue being the WR holder each month!
*   +125 points a month as the full game category record holder.
*   +32.5 points a month as the individual level record holder.

All subsequent runs that are slower than the world record will receive reduced points. Two formulas are used; one if the record is less than 1 minute and above it:
*   Standard Formula (in Python): `math.floor((0.008 * math.pow(math.e, (4.8284 * (wr_time/secs)))) * run_type)`
*   Shorter Formula (in Python): `math.floor((math.pow(math.e, (4.8284 * math.sqrt(wr_time / 60) * (wr_time/pb_secs)))) * run_type`
    *   Reason for this is because the original formula punishes non-record holders a lot harder overall.
  
And how it looks in a simple formula: 
*   Standard:
    *   P = 0.008 * e<sup>4.8284x</sup> * y
        *   x = World Record Seconds (as a float) divided by Personal Best Seconds (as a float)
        *   y = Points based on the type of run it belongs to (see above).
*   Shorter:
    *   P = e<sup>(4.8284 * √(X/60) * (X/Y - 1))</sup> * z
        *   X = World Record Seconds
        *   Y = Personal Best Seconds
        *   Z = Points based on the type of run it belongs to (see above).
  
As an example of how points are reduced, how is a sample based on if a category's world record is 1:20:00:
*   1:20:00 = 1000 points (maximum for full-game)
*   1:25:00 = 752 points
*   1:30:00 = 584 points
*   1:40:00 = 380 points
*   3:00:00 = 68 points
*   4:00:00 = 40 points
*   5:00:00 = 28 points
  
### Installation
1.  Install the requirements above to your computer or server.
2.  Git clone this repo or download a copy with the .ZIP.
    1.  Recommended to create a virutal envionment with `python -m pip venv .` within the directory you want to hold this in.
3.  Open the new folder in a code editor and make whatever changes are needed to `.env.example`, then rename it to JUST `.env`.
4.  Through whatever means, `docker compose up -d --build` to begin pulling the images and packages.
    1.  The PROD file is used for the production server of thps.run, modify as needed for your environment.
5.  After it is opened, access it through `http://localhost:8001/illiad`; if this fails, check system logs. If `DEBUG` in the `.env` file is set to True, then you should see a callback stack of the error.
    1.  The default `localhost:8001`, with `DEBUG` set to `True` will not give you much. This is the backend project, so it has no UI outside of the admin console.
6.  Setup your superuser with `docker exec -it django python3 manage.py createsuperuser` and follow the prompts. After, log into the admin console.
7.  Use `docker exec -it django python3 manage.py init_series --series <SRC_SERIES_ID> --watch` to begin crawling the series to import into your instance.
    > [!IMPORTANT]  
    > This will take a while to complete, depending on the size of your series (how many players, how many leaderboards, how many runs, how many games, etc.). SRC's API throttles hard, but the code is designed
    > to keep this in mind! It will tell you if it is waiting for the rate limit to expire (~75-100 reqs/minute).
8.  If step 7 goes well, your data should be imported! If you have any issues, send logs and everything through an Issue!
    > [!NOTE]
    > If you are wanting a frontend to base things off of, the `thpsrun/frontend` project can be used as a basis. Just keep in mind there is a lot of thps.run-specific things in there :)