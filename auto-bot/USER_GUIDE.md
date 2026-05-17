# Auto Bot — Complete User Guide
### DAS Facebook Tool

---

> **What is this tool?**
> Auto Bot is a helper that reads car information from a dealership website and automatically types it all into Facebook Marketplace for you. Instead of copying and pasting every detail by hand, Auto Bot does it in seconds.

---
---

# ============================================================
# SECTION 1 — FIRST TIME SETUP
# (You only do this once. Skip to Section 2 after that.)
# ============================================================

---

## WINDOWS — First Time Setup

---

### Step 1 — Find the AutoBot.exe File

Your manager will send you a file called **`AutoBot.exe`**.

- If they sent it by **email**: Open the email, click the attachment to download it. It will go to your **Downloads** folder.
- If they shared it on a **USB drive or shared folder**: Copy the file and paste it somewhere easy to find, like your **Desktop**.

> **What is the Desktop?** It is the main screen you see when you minimize all your windows — where you can see your computer's wallpaper/background.

To save it to your Desktop:
1. Find the `AutoBot.exe` file wherever it was sent to you.
2. Right-click on it.
3. Click **Copy**.
4. Right-click on an empty spot on your Desktop.
5. Click **Paste**.

Now `AutoBot.exe` will be sitting on your Desktop where you can easily find it every day.

---

### Step 2 — Open AutoBot.exe for the First Time

1. Look at your Desktop. Find the file named **`AutoBot.exe`**. It may look like a small icon with a robot or a gear.
2. **Double-click** it (click it twice quickly).

**IMPORTANT — Windows Warning Box:**

A blue box may pop up that says **"Windows protected your PC"** and shows a warning message. This is normal. Windows shows this for any new program that hasn't been installed from a big store like the Microsoft Store.

Here is exactly what to do:
1. Look for the words **"More info"** in small text — it is a clickable link inside that blue box. Click it.
2. The box will change and show a button that says **"Run anyway"** at the bottom.
3. Click **"Run anyway"**.

The Auto Bot window will now open.

---

### Step 3 — Enter Your API Key (First Time Only)

The first time you open Auto Bot, it will ask you for an **API Key**.

- An API Key is like a password that lets Auto Bot connect to the AI brain (ChatGPT) that reads the car details.
- Your manager will give you this key. It looks like a long string of letters and numbers starting with **`sk-`**.

Here is what to do:
1. The Auto Bot window will have a text box on the screen.
2. Click inside the text box.
3. Type or paste the API key your manager gave you.
   - To paste: Hold **Ctrl** on your keyboard and press **V** at the same time.
4. Click the button that says **"Save & Start Server"**.
5. A loading bar will appear for a few seconds. Wait for it to finish.

> After this, the key is saved forever on your computer. You will never need to enter it again.

---

### Step 4 — You Will See the Main Window

After the loading bar finishes, the main Auto Bot window will appear. It shows:

- A **green dot** at the top with the words **"Server running · http://127.0.0.1:8000"** — this means everything is working. ✅
- Instructions for setting up the Chrome extension (you will do that next).

> **Leave this window open** the whole time you are working. You can click the minus button ( **—** ) in the top-right corner of the window to minimize it so it is out of your way. Just don't click the **X** to close it.

---

### Step 5 — Install the Chrome Extension (First Time Only)

The Chrome extension is a small add-on that lives inside Google Chrome. It is what gives you the side panel tool. You need to install it once.

**First — Open Google Chrome**

1. Find the **Google Chrome** app on your computer. It is a circle icon that is red, yellow, green, and blue.
2. Double-click it to open Chrome.

**Second — Go to the Chrome Extensions Page**

1. Look at the top of Chrome. You will see a long white bar where you type website addresses. This is called the **address bar**.
2. Click inside that bar so it is highlighted.
3. Delete whatever is in there, then type exactly this:
   ```
   chrome://extensions
   ```
4. Press **Enter** on your keyboard.
5. A page called **"Extensions"** will open. It shows all the add-ons installed in your Chrome.

**Third — Turn On Developer Mode**

1. Look at the **top-right corner** of the Extensions page.
2. You will see a toggle switch labeled **"Developer mode"**.
   - A toggle looks like a small on/off switch, similar to a light switch.
3. Click it so it turns **blue** (that means it is ON).
4. After you click it, three new buttons will appear at the top-left of the page:
   - **Load unpacked**
   - Pack extension
   - Update
   You only need the first one.

**Fourth — Load the Extension**

1. Go back to the **Auto Bot window** on your taskbar (the bar at the bottom of your screen).
2. Find the section that shows the **extension folder path**. It is a long file path that looks something like:
   ```
   C:\Users\YourName\AutoBot\extension
   ```
3. Click the button that says **"Copy Path"**.
   - The button text will briefly change to **"Copied ✓"** to confirm it was copied.

4. Now go back to Chrome on the Extensions page.
5. Click the **"Load unpacked"** button.
6. A **file browser window** will pop open — this is the same type of window you use when you open a file on your computer.
7. Look at the **top** of that file browser window. You will see an address bar (a white bar showing the current folder location).
8. Click inside that address bar at the top of the file browser.
9. Delete whatever text is there.
10. Hold **Ctrl** and press **V** to paste the path you copied.
11. Press **Enter**.
12. The file browser will jump to the Auto Bot extension folder.
13. Click the **"Select Folder"** button (it may also say "Open" depending on your Windows version).

**You should now see "Auto Bot" appear in your list of extensions on the Chrome Extensions page.** ✅

It will show:
- The name **Auto Bot**
- A description saying something about scraping vehicle listings
- A toggle switch that should be turned ON (blue)

---

### Step 6 — Pin Auto Bot to Your Chrome Toolbar

Pinning the extension means its icon will always be visible in Chrome, so you can click it easily every day.

1. Look at the **top-right area of Chrome** — to the right of the address bar.
2. You will see a small **puzzle piece icon** (🧩). Click it.
3. A small menu drops down showing all your extensions.
4. Find **Auto Bot** in that list.
5. Click the **pin icon** (📌) next to Auto Bot.
6. The puzzle piece menu will close.
7. Now look at your Chrome toolbar again — you should see the **Auto Bot icon** permanently visible there. ✅

---

### First Time Setup is Complete!

From now on, you skip everything above. Your daily routine is just:
1. Open `AutoBot.exe`
2. Use Chrome

---
---

# ============================================================
# SECTION 2 — HOW TO USE AUTO BOT EVERY DAY
# ============================================================

---

## Every Day — Step 1: Start Auto Bot First

**Before you do anything in Chrome**, you need to start Auto Bot.

**On Windows:**
1. Find `AutoBot.exe` on your Desktop.
2. Double-click it.
3. The window opens. Wait until you see the **green dot** that says **"Server running"**.
4. Minimize the window (click the **—** button). Don't close it.

You are ready to go.

---

## Every Day — Step 2: Go to the Dealership Website

1. Open **Google Chrome**.
2. In the address bar at the top, type the dealership's website address and press **Enter**.
3. Navigate to the page that shows their **list of cars for sale** — this is usually called "Inventory," "Used Cars," "Our Vehicles," or similar.
4. You should be on a page where you can **see multiple cars listed**, not on a single car's detail page.

> **Why this matters:** Auto Bot scans the whole page to find all the cars at once. You want to be on the page that shows the list, not a single car.

---

## Every Day — Step 3: Open the Auto Bot Side Panel

1. Look at the **top-right area** of Chrome (to the right of the address bar).
2. Find the **Auto Bot icon** that you pinned earlier.
3. **Click it once**.
4. A panel will slide open on the **right side** of Chrome.
   - The left side of Chrome still shows the dealership website.
   - The right side now shows the Auto Bot panel with a **"Scrape this page"** button at the top.

> **If you don't see the icon:** Click the 🧩 puzzle piece icon → find Auto Bot → click the 📌 pin.

---

## Every Day — Step 4: Scrape the Page

"Scraping" just means Auto Bot reads all the car listings on the page.

1. In the Auto Bot panel on the right side of Chrome, look for the button at the very top that says **"Scrape this page"**.
2. Click it.
3. Wait a few seconds — you will see the panel update.
4. Car cards will appear in the panel — one card for each vehicle Auto Bot detected on the page.

Each card shows the car's basic info like:
- A small photo (if available)
- The year, make, and model (for example: "2021 Toyota Camry")
- The price

> **If no cards appear or it shows an error:**
> - Scroll down on the dealership page to make sure all the cars have fully loaded on screen.
> - Then click **"Scrape this page"** again.
> - Make sure the Auto Bot window is still open and running (check the taskbar at the bottom).

---

## Every Day — Step 5: Pick a Car

1. Look through the cards in the Auto Bot panel.
2. Find the car you want to post on Facebook.
3. **Click on that card** once.
4. The panel will change — it now shows a loading message like **"Loading vehicle details…"**
5. Wait about 5–15 seconds. Auto Bot is using AI to read all the details of that car.
6. The panel will fill in with all the car's information:

| Field | What it shows |
|---|---|
| **Title** | The full name (Year Make Model) |
| **Year** | The year of the car |
| **Make** | The brand (Toyota, Ford, etc.) |
| **Model** | The model name (Camry, F-150, etc.) |
| **Price** | The listed price |
| **Mileage** | How many miles on the car |
| **VIN** | The vehicle ID number |
| **Body type** | Sedan, SUV, Truck, etc. |
| **Exterior color** | Outside color |
| **Interior color** | Inside color |
| **Description** | A paragraph description of the car |
| **Photos** | A grid of photos from the listing |

---

## Every Day — Step 6: Review and Fix the Details

Auto Bot is very good but not perfect. Always check the details before posting.

1. **Read through each field.** Does it look right?
2. If anything is wrong or missing:
   - Click directly on that field (the text box).
   - Delete the wrong text and type the correct information.
3. **Check the photos:**
   - You will see a grid of photos below the car details.
   - If a photo looks wrong (a logo, an icon, a blurry image, etc.), click on it to remove it.
   - Good photos are the ones showing the actual car — exterior shots, interior shots, etc.
4. Make sure the **Title**, **Price**, and **Description** look clean and professional.

> **Tip:** The Description field often has a lot of text. You can trim it down to the most important points if you like.

---

## Every Day — Step 7: Send to Facebook

1. At the bottom of the Auto Bot panel, find the large blue button that says **"Send to Facebook"**.
2. Click it.
3. Chrome will automatically open a **new tab**.
4. That new tab will take you to the **Facebook Marketplace vehicle listing page** — this is the form where you create a new listing on Facebook.
5. Wait for the Facebook page to **fully load**. The page has a lot on it so give it 5–10 seconds.

---

## Every Day — Step 8: Let Auto Bot Fill the Facebook Form

1. Once the Facebook page has finished loading, look for a button that says **"Fill from Auto Bot"**.
   - This button appears somewhere on the Facebook form — it may be at the top or floating on the page.
2. Click **"Fill from Auto Bot"**.
3. Watch as the form automatically fills in:
   - The vehicle title
   - The price
   - The mileage
   - The description

> **If "Fill from Auto Bot" doesn't appear:**
> - Wait a bit longer — sometimes Facebook is slow to load.
> - Scroll up and down on the page to look for it.
> - If it still doesn't appear, close the tab and click "Send to Facebook" again in the Auto Bot panel.

> **If a field doesn't fill in correctly:**
> - Simply click on that field in the Facebook form and type the correct info yourself.

---

## Every Day — Step 9: Add Photos to Facebook

Auto Bot fills in the text fields, but you need to **upload photos yourself** on Facebook.

1. On the Facebook listing form, look for the **photo upload area** — it usually says "Add photos" or shows a box with a camera icon.
2. Click it.
3. A file browser window will open.
4. You will need to have the car's photos saved on your computer first.
   - If you need to save them: go back to the dealership website, right-click on each photo, and click **"Save image as"** to save it to your Desktop or Downloads folder.
5. In the file browser, find and select the photos you saved.
6. Click **Open** to upload them.

---

## Every Day — Step 10: Finish and Post the Listing

1. Scroll through the Facebook form and check everything looks good:
   - Title ✓
   - Price ✓
   - Mileage ✓
   - Description ✓
   - Photos ✓
2. Fill in any extra fields Facebook asks for:
   - **Condition** — usually "Used"
   - **Location** — your city
   - Any other required fields (Facebook may prompt you if something is missing)
3. When everything looks good, click the **"Next"** or **"Publish"** button to post the listing.

**The listing is now live on Facebook Marketplace!** 🎉

---

## Every Day — Step 11: Post the Next Car

1. Go back to the Chrome tab that has the dealership website and the Auto Bot panel open.
2. Click the **"← Back to results"** button at the top of the Auto Bot panel.
3. The list of car cards comes back.
4. Click the next car you want to post.
5. Repeat from **Step 6** above.

---
---

# ============================================================
# SECTION 3 — MAC SETUP (Mac users only)
# ============================================================

> Skip this section if you are on Windows.

---

## Mac — First Time Setup

### Step 1 — Check That You Have Python

1. On your Mac, press **Command (⌘) + Space** at the same time. A search bar called Spotlight will appear.
2. Type `Terminal` and press **Enter**. A black or white window will open — this is the Terminal.
3. In the Terminal, type this exactly and press **Enter**:
   ```
   python3 --version
   ```
4. If you see something like `Python 3.10.x`, you are good. ✅
5. If you see an error, go to `https://python.org`, click **Downloads**, download the installer, and run it. Then come back here.

### Step 2 — Install the Required Tools

1. In Terminal, copy and paste this line exactly, then press **Enter**:
   ```
   pip3 install fastapi uvicorn openai requests beautifulsoup4
   ```
2. Wait 1–3 minutes while it installs. You will see a lot of text scrolling. That is normal.
3. When it finishes and you see a `$` symbol again, it is done. ✅

### Step 3 — Put the Auto Bot Folder in Your Documents

1. Your manager will share a folder called **`auto-bot`**.
2. Copy that folder into your **Documents** folder.
   - Open Finder (the smiley face icon in your dock at the bottom).
   - Click **Documents** on the left side.
   - Drag the `auto-bot` folder into Documents.

### Step 4 — Set Your API Key

1. Open Terminal.
2. Copy and paste this line, but **replace `YOUR-KEY-HERE`** with the actual API key your manager gave you:
   ```
   echo 'export OPENAI_API_KEY="YOUR-KEY-HERE"' >> ~/.zshrc && source ~/.zshrc
   ```
3. Press **Enter**.
4. This saves your API key permanently. You only do this once.

---

## Mac — Starting Auto Bot Every Day

1. Open **Terminal** (Command + Space → type Terminal → Enter).
2. Copy and paste this line and press **Enter**:
   ```
   cd ~/Documents/auto-bot/api && uvicorn main:app
   ```
3. You will see text appear. When you see the line:
   ```
   Application startup complete.
   ```
   Auto Bot is running. ✅
4. **Leave Terminal open** while you work. Do not close it.

Now go back to **Section 2 — How to Use Auto Bot Every Day** and follow those steps in Chrome.

When you are done for the day:
1. Click on the Terminal window.
2. Hold **Control** and press **C** to stop Auto Bot.
3. Close Terminal.

---

## Mac — Chrome Extension Setup (First Time Only)

The Chrome extension setup is the **same on Mac as on Windows**. Follow the exact same steps from **Section 1, Steps 5 and 6** above, starting from "Go to the Chrome Extensions Page."

The only difference: when you click **"Copy Path"** in the Auto Bot window, the path will look like `/Users/YourName/AutoBot/extension` instead of `C:\Users\...`.

---
---

# ============================================================
# SECTION 4 — QUICK REFERENCE
# ============================================================

---

## Your Daily Checklist

Every time you sit down to post cars, do these things in order:

```
[ ] 1. Open AutoBot.exe (Windows) OR start Terminal command (Mac)
[ ] 2. Wait for green "Server running" dot
[ ] 3. Open Google Chrome
[ ] 4. Go to dealership inventory page
[ ] 5. Click the Auto Bot icon in Chrome toolbar
[ ] 6. Click "Scrape this page"
[ ] 7. Click on a car card
[ ] 8. Review and fix the details
[ ] 9. Click "Send to Facebook"
[ ] 10. On Facebook, click "Fill from Auto Bot"
[ ] 11. Upload photos manually
[ ] 12. Click Publish
[ ] 13. Go back and do the next car
```

---

## Troubleshooting — Common Problems

---

**Problem: Windows shows a blue warning box when I open AutoBot.exe**
- Click **"More info"** (it is a small clickable link inside the box)
- Then click **"Run anyway"**

---

**Problem: Auto Bot window shows a red dot or says "Server not running"**
- Close the Auto Bot window completely
- Double-click AutoBot.exe again to restart it
- Wait for the green dot to appear before going to Chrome

---

**Problem: I don't see the Auto Bot icon in Chrome**
- Click the 🧩 puzzle piece icon in the top-right of Chrome
- Find Auto Bot in the list
- Click the 📌 pin icon next to it

---

**Problem: I click "Scrape this page" and nothing happens / no cars appear**
- Make sure the Auto Bot window is open and shows the green dot
- Scroll down on the dealership website to load all the cars, then click Scrape again
- Try refreshing the dealership page (press F5) and then click Scrape again

---

**Problem: The car details filled in look wrong**
- Just click on any field and fix it manually — type the correct information
- Auto Bot's job is to save you most of the work. A few manual fixes are totally normal.

---

**Problem: "Fill from Auto Bot" button doesn't appear on Facebook**
- Wait longer — Facebook can be slow to load. Give it 15–20 seconds.
- Scroll up to the very top of the Facebook form page
- If it still isn't there, close the Facebook tab and click "Send to Facebook" again in the Auto Bot panel

---

**Problem: I closed Auto Bot by mistake while working**
- Double-click AutoBot.exe to reopen it
- Go back to Chrome — the extension is still there
- You may need to click "Scrape this page" again to reload the cars

---

**Problem: I need to change my API key**
- Open Auto Bot
- Click the **"Change API Key"** button
- Enter the new key and click Save

---

*For any other problems, contact IT support (Bryan).*

---

*Auto Bot — DAS Facebook Tool*
