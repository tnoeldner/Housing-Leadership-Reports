from pathlib import Path
import json

def load_rubric(rubric_path):
    with open(rubric_path, 'r') as file:
        return file.read()

def generate_ai_prompt(staff_member, rubric_scores):
    ascend_rubric = load_rubric(Path('../rubrics/ascend_rubric.md'))
    north_rubric = load_rubric(Path('../rubrics/north_rubric.md'))
    
    prompt = f"""
    Evaluate the following staff member based on the ASCEND and NORTH criteria:

    Staff Member: {staff_member['name']}
    ASCEND Score: {rubric_scores['ascend']}
    NORTH Score: {rubric_scores['north']}

    ASCEND Rubric:
    {ascend_rubric}

    NORTH Rubric:
    {north_rubric}

    Based on the above information, provide a summary of how this staff member exemplifies the ASCEND and NORTH criteria.
    """
    return prompt.strip()

def select_best_representative(staff_members):
    best_member = None
    highest_score = -1

    for member in staff_members:
        total_score = member['rubric_scores']['ascend'] + member['rubric_scores']['north']
        if total_score > highest_score:
            highest_score = total_score
            best_member = member

    return best_member

def create_summary_for_best_representative(staff_members):
    best_member = select_best_representative(staff_members)
    if best_member:
        prompt = generate_ai_prompt(best_member, best_member['rubric_scores'])
        return prompt
    return "No staff members available for evaluation."