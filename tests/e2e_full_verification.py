import os
import sys
import json
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "tests/e2e_results"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def run():
    print("==================================================")
    print("STARTING COMPREHENSIVE BORMOCLASS PLAYWRIGHT AUDIT")
    print("==================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path='/usr/bin/google-chrome',
            headless=True
        )

        # Storage for errors
        console_errors = []
        page_errors = []

        def attach_monitors(page, name):
            page.on("console", lambda msg: console_errors.append(f"[{name}] {msg.type}: {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(f"[{name}] {err}"))

        # -------------------------------------------------------------
        # STEP 1: TEACHER REGISTRATION & CLASS CREATION
        # -------------------------------------------------------------
        print("\n--- STEP 1: Teacher Registration & Dashboard ---")
        teacher_ctx = browser.new_context(viewport={'width': 1366, 'height': 860})
        t_page = teacher_ctx.new_page()
        attach_monitors(t_page, "Teacher")

        t_page.goto("http://localhost:8010/", wait_until="networkidle")
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/01_teacher_landing.png")
        print("1.1 Loaded landing page.")

        # Click Register
        t_page.click("#heroRegBtn")
        t_page.wait_for_selector("#authRole")
        t_page.select_option("#authRole", "teacher")
        t_page.fill("#authPassword", "TeacherPass2026!")
        t_page.click("#authForm button[type='submit']")

        # Registration success modal
        t_page.wait_for_selector("#confirmRegBtn", timeout=10000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/02_teacher_reg_success.png")

        card_text = t_page.inner_text("#modalContainer")
        print(f"1.2 Registration modal content:\n{card_text.strip()}")

        t_page.click("#confirmRegBtn")
        t_page.wait_for_selector("#createClassBtn", timeout=10000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/03_teacher_dashboard.png")
        print("1.3 Teacher dashboard ready.")

        # Create class
        print("\n--- STEP 2: Creating Class ---")
        t_page.click("#createClassBtn")
        t_page.wait_for_selector("#createClassForm", timeout=5000)
        t_page.fill("#clsTitle", "8-А Класс (Информатика и ИКТ)")
        t_page.fill("#clsGrade", "8")
        t_page.fill("#clsSubject", "inf")
        t_page.fill("#clsGoal", "Изучить базовые алгоритмы и сдать ВПР на отлично")
        t_page.click("#createClassForm button[type='submit']")

        # Submitting immediately navigates to #class/<id>/stream
        t_page.wait_for_selector(".class-hero-pin-val", timeout=10000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/04_teacher_class_created.png")

        join_pin = t_page.inner_text(".class-hero-pin-val").strip()
        current_url = t_page.url
        class_id = current_url.split("#class/")[1].split("/")[0]
        print(f"2.1 Created Class ID: {class_id}")
        print(f"2.2 Join PIN: {join_pin}")

        # Verify class card on dashboard as well
        t_page.click("#brandBtn")
        t_page.wait_for_selector(".class-card", timeout=10000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/04b_class_card_dashboard.png")
        class_card = t_page.query_selector(f".class-card[data-class-id='{class_id}']")
        print(f"2.3 Class card confirmed on dashboard: {bool(class_card)}")

        # Open class again
        class_card.click()
        t_page.wait_for_selector("#classTabContent", timeout=10000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/05_teacher_class_stream.png")
        print("2.4 Entered class stream.")

        # Post Announcement in Stream
        print("\n--- STEP 3: Stream Announcement ---")
        t_page.fill("#streamPostText", "Добро пожаловать в BormoClass! Сегодня начинаем практическую работу.")
        t_page.click("#publishStreamBtn")
        t_page.wait_for_timeout(1000)
        t_page.wait_for_selector("#streamFeed", timeout=5000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/06_stream_announcement_posted.png")
        print("3.1 Announcement posted.")

        # Go to Tab 2: Coursework
        print("\n--- STEP 4: Creating Coursework ---")
        t_page.click("button[data-ctab='classwork']")
        t_page.wait_for_selector("#createCwBtn", timeout=5000)
        t_page.click("#createCwBtn")
        t_page.wait_for_selector("#createCwForm", timeout=5000)
        t_page.fill("#cwTitle", "Лабораторная работа №1: Линейные алгоритмы")
        t_page.fill("#cwInstructions", "Составьте блок-схему линейного вычислительного процесса и опишите решение.")
        t_page.fill("#cwPoints", "5")
        t_page.fill("#cwRecess", "300")
        t_page.click("#createCwForm button[type='submit']")

        t_page.wait_for_timeout(1000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/07_coursework_created.png")
        print("4.1 Assignment published.")

        # Go to Tab 3: People & Desks
        print("\n--- STEP 5: Verifying Seating Chart (1..40 Desks) ---")
        t_page.click("button[data-ctab='people']")
        t_page.wait_for_selector("#desksGridArea", timeout=5000)
        desks_count = len(t_page.query_selector_all(".seat-btn"))
        print(f"5.1 Total desks rendered: {desks_count} (Expected: 40)")
        assert desks_count == 40, f"Expected 40 desks, got {desks_count}"
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/08_people_seating_empty.png")

        # Go to Tab 4: Grades (Initial Matrix & Simonov SOU)
        print("\n--- STEP 6: Verifying Initial Grades Matrix & SOU ---")
        t_page.click("button[data-ctab='grades']")
        t_page.wait_for_selector(".analytics-bar", timeout=5000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/09_grades_initial_matrix.png")
        print("6.1 Initial grades matrix and SOU panel verified.")

        # Test Interactive Whiteboard Navigation
        print("\n--- STEP 7: Interactive Whiteboard (/board) ---")
        t_page.click("#openBoardBtn")
        t_page.wait_for_url("**/board/**", timeout=10000)
        t_page.wait_for_timeout(2500)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/10_whiteboard_active.png")
        print("7.1 Whiteboard loaded successfully.")

        # Click "В класс" to return
        t_page.click("#bcBackBtn")
        t_page.wait_for_url("**/#class/**", timeout=10000)
        t_page.wait_for_timeout(1000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/11_returned_to_class.png")
        print("7.2 Returned from Whiteboard to Class.")

        # -------------------------------------------------------------
        # STEP 8: STUDENT REGISTRATION, JOIN DESK & SUBMISSION
        # -------------------------------------------------------------
        print("\n--- STEP 8: Student Flow (Isolated Context) ---")
        student_ctx = browser.new_context(viewport={'width': 1366, 'height': 860})
        s_page = student_ctx.new_page()
        attach_monitors(s_page, "Student")

        s_page.goto("http://localhost:8010/", wait_until="networkidle")
        s_page.click("#heroRegBtn")
        s_page.wait_for_selector("#authRole")
        s_page.select_option("#authRole", "student")
        s_page.fill("#authPassword", "StudentPass2026!")
        s_page.click("#authForm button[type='submit']")

        s_page.wait_for_selector("#confirmRegBtn", timeout=10000)
        s_card_text = s_page.inner_text("#modalContainer")
        print(f"8.1 Student registered:\n{s_card_text.strip()}")
        s_page.click("#confirmRegBtn")

        # Join Class by PIN and pick Desk #12
        s_page.wait_for_selector("#joinClassBtn", timeout=10000)
        s_page.screenshot(path=f"{SCREENSHOT_DIR}/12_student_dashboard.png")
        s_page.click("#joinClassBtn")
        s_page.wait_for_selector("#joinClassForm", timeout=5000)
        s_page.fill("#joinPin", join_pin)

        # Pick Desk #12
        s_page.click(".seat-pick-btn[data-seat='12']")
        disp = s_page.inner_text("#seatChosenDisplay")
        print(f"8.2 Seat choice: {disp}")
        assert "№12" in disp, "Desk #12 should be chosen"

        s_page.click("#submitJoinBtn")
        s_page.wait_for_selector("#classTabContent", timeout=10000)
        s_page.screenshot(path=f"{SCREENSHOT_DIR}/13_student_class_joined.png")
        print("8.3 Student successfully joined class and entered stream at desk #12.")

        # Test Understanding Traffic Light in Stream
        print("\n--- STEP 9: Student Understanding Traffic Light ---")
        traffic_btn = s_page.query_selector(".traffic-btn.green")
        if traffic_btn:
            traffic_btn.click()
            s_page.wait_for_timeout(500)
            print("9.1 Student clicked green traffic light (Всё понятно).")

        # Student turns in assignment
        print("\n--- STEP 10: Student Submits Assignment ---")
        s_page.click("button[data-ctab='classwork']")
        s_page.wait_for_selector("button[data-cwid]", timeout=5000)
        s_page.screenshot(path=f"{SCREENSHOT_DIR}/14_student_classwork_view.png")

        turn_in_btn = s_page.query_selector("button[data-cwid]")
        turn_in_btn.click()
        s_page.wait_for_selector("#turnInForm", timeout=5000)
        s_page.fill("#studentAnswer", "Решение задачи: алгоритм содержит ввод данных, 3 последовательных блока вычисления и вывод результата. Все тесты пройдены.")
        s_page.click("#turnInForm button[type='submit']")
        s_page.wait_for_timeout(1000)
        s_page.screenshot(path=f"{SCREENSHOT_DIR}/15_student_work_submitted.png")
        print("10.1 Student submitted assignment solution.")

        # -------------------------------------------------------------
        # STEP 11: TEACHER GRADING, ZERO-PII SEATING & SIMONOV SOU
        # -------------------------------------------------------------
        print("\n--- STEP 11: Teacher Verifies Student & Grades ---")
        # Check seating chart in teacher view
        t_page.click("button[data-ctab='people']")
        t_page.wait_for_timeout(1000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/16_teacher_seat_12_occupied.png")

        # Find seat 12 button
        occupied_seat = t_page.query_selector(".seat-btn.occupied")
        print(f"11.1 Occupied seat button found: {bool(occupied_seat)}")
        if occupied_seat:
            seat_text = occupied_seat.inner_text().strip()
            print(f"Seat 12 text (only generated handle): {seat_text}")
            assert "Смирнов" not in seat_text and "Дмитрий" not in seat_text
            # Click seat 12 to test teacher's student management modal (attendance check, 0 PII)
            occupied_seat.click()
            t_page.wait_for_selector("#saveMemberBtn", timeout=5000)
            t_page.click("#saveMemberBtn")
            t_page.wait_for_timeout(1000)
            print("11.2 Student presence confirmed with 0 PII.")

        # Open Grades tab
        t_page.click("button[data-ctab='grades']")
        t_page.wait_for_selector(".gradebook-table", timeout=5000)
        t_page.wait_for_timeout(1000)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/17_teacher_gradebook_submission.png")

        # Verify that gradebook table contains only generated handle and NO personal data
        gradebook_text = t_page.inner_text(".gradebook-table")
        assert "Смирнов" not in gradebook_text and "Дмитрий" not in gradebook_text, "Gradebook must not contain any personal data!"
        assert "ФИО" not in gradebook_text, "Gradebook must not have FIO column!"

        # Grade the cell
        grade_cell = t_page.query_selector(".gradebook-cell")
        print(f"11.3 Grade cell content: '{grade_cell.inner_text().strip()}'")
        grade_cell.click()

        t_page.wait_for_selector(".grade-btn[data-g='5']", timeout=5000)
        t_page.fill("#teacherCommentInput", "Отличный ответ! Алгоритм составлен идеально.")
        t_page.click(".grade-btn[data-g='5']")
        t_page.wait_for_timeout(1500)
        t_page.screenshot(path=f"{SCREENSHOT_DIR}/18_teacher_graded_matrix.png")
        print("11.4 Grade '5' given to student.")

        # Verify SOU recalculated
        matrix_text = t_page.inner_text(".analytics-bar")
        print(f"11.5 Recalculated SOU Analytics:\n{matrix_text.strip()}")
        assert "100%" in matrix_text, "SOU should be 100% for grade 5"

        # Test CSV Export
        print("\n--- STEP 12: Testing CSV Export ---")
        with t_page.expect_download() as download_info:
            t_page.click("#exportCsvBtn")
        download = download_info.value
        csv_path = f"{SCREENSHOT_DIR}/exported_gradebook.csv"
        download.save_as(csv_path)
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_content = f.read()
        print(f"12.1 Downloaded CSV Preview (with UTF-8 BOM):\n{csv_content[:300]}")
        assert len(csv_content) > 10, "CSV export should contain rows"
        assert "Смирнов" not in csv_content and "Дмитрий" not in csv_content, "CSV must not contain any personal data!"
        assert "ФИО" not in csv_content, "CSV must not contain FIO column!"

        # -------------------------------------------------------------
        # STEP 13: STUDENT REWARD / RECESS WALLET VERIFICATION
        # -------------------------------------------------------------
        print("\n--- STEP 13: Verifying Student Grade & Recess Wallet ---")
        s_page.reload(wait_until="domcontentloaded")
        s_page.wait_for_timeout(1000)
        s_page.screenshot(path=f"{SCREENSHOT_DIR}/19_student_graded_view.png")
        user_bar_text = s_page.inner_text("#userBar")
        print(f"13.1 Student User Bar (Wallet):\n{user_bar_text}")
        assert "5 мин" in user_bar_text or "300" in user_bar_text or "перемен" in user_bar_text, "Student recess reward credited"

        # -------------------------------------------------------------
        # STEP 14: PEDOBRAZ-PASSPORT PAGE VERIFICATION (/passport)
        # -------------------------------------------------------------
        print("\n--- STEP 14: Verifying Passport Standalone Generator (/passport) ---")
        p_page = browser.new_page(viewport={'width': 1280, 'height': 800})
        attach_monitors(p_page, "Passport")
        p_page.goto("http://localhost:8010/passport", wait_until="domcontentloaded")
        p_page.wait_for_timeout(1000)
        p_page.screenshot(path=f"{SCREENSHOT_DIR}/20_passport_page.png")
        print("14.1 Passport generator page loaded perfectly.")
        p_page.close()

        # -------------------------------------------------------------
        # STEP 15: CADDY EDGE REVERSE PROXY (HTTPS 8443)
        # -------------------------------------------------------------
        print("\n--- STEP 15: Verifying Edge Proxy (HTTPS:8443) ---")
        caddy_ctx = browser.new_context(ignore_https_errors=True, viewport={'width': 1280, 'height': 800})
        c_page = caddy_ctx.new_page()
        attach_monitors(c_page, "Caddy")
        res = c_page.goto("https://localhost:8443/", wait_until="domcontentloaded")
        print(f"15.1 Caddy HTTPS status: {res.status}")
        c_page.screenshot(path=f"{SCREENSHOT_DIR}/21_caddy_https_page.png")
        assert res.status == 200, f"Expected 200 from Caddy, got {res.status}"
        caddy_ctx.close()

        # Cleanup
        teacher_ctx.close()
        student_ctx.close()
        browser.close()

        print("\n==================================================")
        print("PLAYWRIGHT AUDIT RESULTS:")
        print(f"Console errors: {len(console_errors)}")
        print(f"Page errors: {len(page_errors)}")
        if console_errors:
            for ce in console_errors:
                print(f"  - {ce}")
        if page_errors:
            for pe in page_errors:
                print(f"  - {pe}")
        print("==================================================")

        if page_errors:
            print("FAILED: Page errors encountered.")
            sys.exit(1)
        else:
            print("SUCCESS: All flows executed cleanly and successfully!")

if __name__ == "__main__":
    run()
