from pathlib import Path
import json

def load_rubric(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def load_rubric_config(config_path):
    with open(config_path, 'r') as file:
        return json.load(file)

def get_best_representative(reports, ascend_rubric, north_rubric):
    best_score = -1
    best_member = None

    for report in reports:
        score = evaluate_report(report, ascend_rubric, north_rubric)
        if score > best_score:
            best_score = score
            best_member = report['staff_member']

    return best_member

def evaluate_report(report, ascend_rubric, north_rubric):
    # Placeholder for evaluation logic based on rubrics
    ascend_score = calculate_score(report, ascend_rubric)
    north_score = calculate_score(report, north_rubric)
    return ascend_score + north_score

def calculate_score(report, rubric):
    # Placeholder for score calculation logic
    score = 0
    # Implement scoring based on rubric criteria
    return score

def load_reports(reports_directory):
    reports = []
    for report_file in Path(reports_directory).glob('*.json'):
        with open(report_file, 'r') as file:
            reports.append(json.load(file))
    return reports