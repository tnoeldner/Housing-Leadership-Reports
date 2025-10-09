# Rubrics Integration Project

This project aims to integrate ASCEND and NORTH evaluation rubrics into a reporting system for staff performance assessment. The rubrics will be used to analyze submitted reports and identify staff members who best represent the criteria outlined in the rubrics.

## Project Structure

- **rubrics/**
  - `ascend_rubric.md`: Detailed rubric for evaluating staff performance based on ASCEND criteria.
  - `north_rubric.md`: Detailed rubric for evaluating staff performance based on NORTH criteria.
  - `rubric_config.json`: Configuration file defining the structure and settings for the rubrics.

- **src/**
  - `rubric_analyzer.py`: Functions and classes for analyzing reports against the rubrics.
  - `ai_prompts.py`: AI prompts for generating summaries and evaluations based on rubric analysis.
  - `utils.py`: Utility functions for loading rubrics and processing data.

- **config/**
  - `evaluation_settings.json`: Configuration settings for the evaluation process.

- **requirements.txt**: Lists the Python dependencies required for the project.

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd rubrics-integration
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Review the rubrics located in the `rubrics` directory to understand the evaluation criteria.

4. Configure any necessary settings in `config/evaluation_settings.json` to tailor the evaluation process to your needs.

## Usage Guidelines

- Use the `rubric_analyzer.py` to analyze submitted reports against the ASCEND and NORTH rubrics.
- The AI prompts defined in `ai_prompts.py` can be utilized to generate summaries based on the rubric evaluations.
- Ensure that the rubrics are updated in the `rubrics` directory as needed to reflect any changes in evaluation criteria.

## Purpose

The purpose of this project is to provide a structured approach to evaluating staff performance using defined rubrics, facilitating a fair and consistent assessment process. By integrating AI capabilities, the project aims to streamline the evaluation process and enhance reporting accuracy.