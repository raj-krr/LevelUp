"""Helper script to generate clean demo homework images for testing and presentations."""

import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs("sample_tests", exist_ok=True)


def create_image_with_text(filename, title, lines, bg_color="#FAF7F2", text_color="#5C4A3A"):
    img = Image.new("RGB", (800, 600), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Header border
    draw.rectangle([20, 20, 780, 580], outline="#4A5D3A", width=3)
    draw.rectangle([20, 20, 780, 90], fill="#4A5D3A")
    draw.text((40, 40), title, fill="#FFFDF7")

    y = 130
    for line in lines:
        draw.text((50, y), line, fill=text_color)
        y += 40

    img.save(os.path.join("sample_tests", filename))
    print(f"Generated sample_tests/{filename}")


# 1. Printed Math Problem (Grade 5)
create_image_with_text(
    "1_math_word_problem_grade5.jpg",
    "GRADE 5 MATHEMATICS - FRACTIONS & SHARING",
    [
        "Question 3:",
        "Rohan has 3/4 of a chocolate bar.",
        "He gives 1/2 of what he has to his sister Priya.",
        "",
        "a) What fraction of the whole chocolate bar does Priya get?",
        "b) What fraction of the chocolate bar is left with Rohan?",
        "",
        "Show all your calculation steps clearly."
    ]
)

# 2. Handwritten Math Problem
create_image_with_text(
    "2_handwritten_math.jpg",
    "HOMEWORK - DIVISION WORK",
    [
        "Problem 7:",
        "456 divided by 12 = ?",
        "",
        "Student's attempt:",
        "  12 ) 456 ( 35",
        "     - 36",
        "     ----",
        "       96",
        "     - 60",
        "     ----",
        "       36"
    ]
)

# 3. Science Diagram Question
create_image_with_text(
    "3_science_water_cycle.jpg",
    "GRADE 6 SCIENCE - WATER CYCLE",
    [
        "Chapter 8: Water In Nature",
        "",
        "1. Identify the process where water changes into vapor due to heat from the sun.",
        "2. What is the process of water vapor cooling down to form droplets?",
        "3. Explain why rainfall is important for groundwater recharge in 2-3 sentences."
    ]
)

# 4. Multi-Question Page
create_image_with_text(
    "4_multiple_questions_page.jpg",
    "WORKSHEET - MIXED REVISION",
    [
        "Q1. Find the Perimeter of a rectangle with length 14 cm and breadth 9 cm.",
        "",
        "Q2. A train leaves Station A at 08:30 AM and reaches Station B at 11:15 AM.",
        "    How long did the journey take?",
        "",
        "Q3. Convert 3.75 kilograms into grams."
    ]
)

# 5. Non-Homework Image
create_image_with_text(
    "5_not_homework.jpg",
    "INDOOR GARDENING TIPS",
    [
        "Monstera Deliciosa Care Guide:",
        "- Water once every 7 to 10 days.",
        "- Provide bright, indirect sunlight.",
        "- Wipe leaves gently with a damp cloth."
    ],
    bg_color="#EBF4EB",
    text_color="#2D5A27"
)

if __name__ == "__main__":
    print("All sample demo images created successfully in sample_tests/")

