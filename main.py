import json
import os
from pathlib import Path
import random

from nicegui import ui
import pydantic

PROGRESS_FILE = 'progress.json'
EXAMS_DIR = 'exams'


class Card(pydantic.BaseModel):
  question: str
  options: list[str]
  answers: list[int]


# Persistence helpers
def load_progress() -> dict:
  try:
    with open(PROGRESS_FILE) as f:
      return json.load(f)
  except FileNotFoundError:
    return {}


def save_progress(
  test_name: str,
  card_order: list[int],
  correct_order: list[int],
) -> None:
  data = load_progress()
  data[test_name] = {
    'card_order': card_order,
    'correct_order': correct_order,
  }
  with open(PROGRESS_FILE, 'w') as f:
    json.dump(data, f)


def get_exam_files() -> list[str]:
  return sorted(_file.stem for _file in Path(EXAMS_DIR).glob('*.json'))


def load_exam(test_name: str) -> list[Card]:
  filepath = os.path.join(EXAMS_DIR, f'{test_name}.json')
  with open(filepath, encoding='utf-8') as f:
    questions = json.load(f)
  return [Card(**question) for question in questions]


class FlashCardApp:
  def __init__(self):
    self.test_name: str = ''
    self.flash_cards: list[dict] = []  # [{'index': int, 'card': Card}]
    self.correct_indices: set[int] = set()
    self.last_is_correct = False
    self.root: ui.element

  def start(self, test_name: str, fresh: bool):
    self.test_name = test_name
    cards = load_exam(test_name)
    ordered = [
      {'index': index, 'card': card} for index, card in enumerate(cards)
    ]

    progress = load_progress()
    saved = progress.get(test_name)

    if not fresh and saved:
      index_map = {card['index']: card for card in ordered}
      self.flash_cards = [
        index_map[index] for index in saved['card_order'] if index in index_map
      ]
      self.correct_indices = set(saved['correct_order'])
    else:
      self.flash_cards = ordered[:]
      random.shuffle(self.flash_cards)
      self.correct_indices = set()
      # Immediately wipe any old progress for this test
      save_progress(test_name, [card['index'] for card in self.flash_cards], [])

    self.root.clear()
    with self.root:
      self._render_quiz()

  def _save(self):
    save_progress(
      self.test_name,
      [c['index'] for c in self.flash_cards],
      list(self.correct_indices),
    )

  # Card logic
  @property
  def current(self) -> dict:
    return self.flash_cards[-1]

  def _check_answer(self, selected: list[str]) -> bool:
    card = self.current['card']
    correct = {card.options[i] for i in card.answers}
    return set(selected) == correct

  def _place_card_back(self, is_correct: bool):
    card = self.flash_cards.pop()
    num_cards = len(self.flash_cards)
    if is_correct:
      index = 0
    elif num_cards > 50:
      index = random.randint(
        num_cards - (num_cards // 4),
        max(num_cards - 4, 0),
      )
    else:
      index = random.randint(
        num_cards // 2,
        max(num_cards - 4, 0),
      )
    self.flash_cards.insert(index, card)

  # Quiz UI
  def _render_quiz(self):
    card = self.current['card']
    idx = self.current['index']
    choices = card.options[:]
    random.shuffle(choices)
    correct_answers = [card.options[i] for i in card.answers]
    is_multi = len(card.answers) > 1

    # Back to menu
    with ui.row().classes('w-full justify-between items-center mb-4'):
      ui.label(self.test_name).classes('text-lg font-bold text-gray-300')
      ui.button('← Menu', on_click=self._render_menu).props('flat dense')

    # Question
    ui.label(card.question).classes(
      'text-lg font-semibold whitespace-pre-wrap mb-4'
    )

    # Options
    if is_multi:
      checkboxes = [ui.checkbox(c).classes('text-base') for c in choices]
      get_selected = lambda: [cb.text for cb in checkboxes if cb.value]
    else:
      radio = ui.radio(choices, value=None).classes('text-base')
      get_selected = lambda: [radio.value] if radio.value else []

    # Buttons row
    with ui.row().classes('mt-5 gap-3'):
      submit_btn = ui.button('Check Answer').classes(
        'text-black text-base px-5 py-2'
      )
      next_btn = (
        ui.button('Next Card →')
        .props('outline')
        .classes('text-base px-5 py-2 hidden')
      )

    ui.separator().classes('my-4')

    # Fixed-height result panel (always rendered, filled on submit)
    with ui.row().classes(
      'w-full items-start justify-between px-4 py-3 rounded-xl'
      ' bg-gray-800 min-h-[80px]'
    ):
      with ui.column().classes('gap-1'):
        status_label = ui.label('').classes('text-xl font-bold')
        answer_title = ui.label('Correct answer(s):').classes(
          'text-sm text-gray-400 hidden'
        )
        ans_labels = [
          ui.label(f'{answer}').classes('ml-3 text-sm text-gray-200 hidden')
          for answer in correct_answers
        ]
      progress_label = ui.label(
        f'✅ {len(self.correct_indices)} / {len(self.flash_cards)}'
      ).classes('text-base text-gray-400 font-medium whitespace-nowrap mt-1')

    # Callbacks
    def on_submit():
      selected = get_selected()
      is_correct = self._check_answer(selected)
      self.last_is_correct = is_correct

      if is_correct:
        self.correct_indices.add(idx)
        status_label.set_text('✅ CORRECT!')
        status_label.classes(remove='text-red-500')
        status_label.classes(add='text-green-400')
      else:
        self.correct_indices.discard(idx)
        status_label.set_text('❌ INCORRECT!')
        status_label.classes(remove='text-green-400')
        status_label.classes(add='text-red-500')

      progress_label.set_text(
        f'✅ {len(self.correct_indices)} / {len(self.flash_cards)}'
      )
      answer_title.classes(remove='hidden')
      for lbl in ans_labels:
        lbl.classes(remove='hidden')

      submit_btn.set_visibility(False)
      next_btn.classes(remove='hidden')
      self._save()

    def on_next():
      self._place_card_back(self.last_is_correct)
      self.root.clear()
      with self.root:
        self._render_quiz()

    submit_btn.on_click(on_submit)
    next_btn.on_click(on_next)

  # Menu UI
  def _render_menu(self):
    self.root.clear()
    with self.root:
      progress = load_progress()
      exams = get_exam_files()

      if not exams:
        ui.label('No exam files found in the exams/ folder.').classes(
          'text-gray-400'
        )
        return

      for test_name in exams:
        saved = progress.get(test_name)
        has_progress = bool(saved)

        with ui.card().classes('w-full mb-4 p-4 bg-gray-800 rounded-xl'):
          with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-0.5'):
              ui.label(test_name).classes('text-base font-semibold')
              if has_progress:
                n_correct = len(saved['correct_order'])
                n_total = len(saved['card_order'])
                ui.label(f'Progress: ✅ {n_correct} / {n_total}').classes(
                  'text-sm text-gray-400'
                )
              else:
                ui.label('No saved progress').classes('text-sm text-gray-500')

            with ui.row().classes('gap-2'):
              if has_progress:
                ui.button(
                  'Resume',
                  on_click=lambda t=test_name: self.start(t, fresh=False),
                ).props('outline').classes('text-sm')
              ui.button(
                'Start New',
                on_click=lambda t=test_name: self._confirm_new(t, has_progress),
              ).classes('text-sm')

  def _confirm_new(self, test_name: str, warn: bool):
    if not warn:
      self.start(test_name, fresh=True)
      return

    with ui.dialog() as dialog, ui.card().classes('p-6 bg-gray-800'):
      ui.label('Start new session?').classes('text-lg font-bold mb-2')
      ui.label(
        'This will overwrite your saved progress for this test.'
      ).classes('text-sm text-gray-400 mb-4')
      with ui.row().classes('gap-3'):
        ui.button('Cancel', on_click=dialog.close).props('flat')
        ui.button(
          'Yes, start new',
          on_click=lambda: (dialog.close(), self.start(test_name, fresh=True)),
        )
    dialog.open()


@ui.page('/')
def index():
  ui.query('body').classes('bg-gray-900')
  with ui.card().classes('max-w-5xl mx-auto mt-10 p-8 shadow-xl rounded-2xl'):
    app.root = ui.column().classes('w-full')
    app._render_menu()


app = FlashCardApp()
ui.run(title='Flash Cards', port=8080, dark=True)
