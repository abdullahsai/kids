import os
import random
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload

DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(os.getcwd(), "quiz.db"))

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'super-secret-key')

    db.init_app(app)

    with app.app_context():
        db_directory = os.path.dirname(DATABASE_PATH)
        if db_directory and not os.path.exists(db_directory):
            os.makedirs(db_directory, exist_ok=True)
        db.create_all()

    register_routes(app)
    return app


db = SQLAlchemy()


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    correct_answer = db.Column(db.String(255), nullable=False)

    options = db.relationship('AnswerOption', backref='question', cascade='all, delete-orphan')


class AnswerOption(db.Model):
    __tablename__ = 'answer_options'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)


def register_routes(app: Flask) -> None:
    @app.route('/', methods=['GET', 'POST'])
    def quiz():
        question = Question.query.options(joinedload(Question.options)).order_by(Question.id).first()
        if not question:
            return render_template('empty_quiz.html')

        feedback = None
        is_correct = None

        if request.method == 'POST':
            selected_option = request.form.get('answer')
            is_correct = selected_option == question.correct_answer
            if is_correct:
                feedback = 'إجابة صحيحة! أحسنت.'
            else:
                feedback = 'إجابة غير صحيحة، حاول مرة أخرى!'

        incorrect_pool = [opt.text for opt in question.options if not opt.is_correct]
        random.shuffle(incorrect_pool)
        incorrect_choices = incorrect_pool[:3]

        if len(incorrect_choices) < 3:
            if incorrect_pool:
                incorrect_choices.extend(
                    random.choices(incorrect_pool, k=3 - len(incorrect_choices))
                )
            else:
                incorrect_choices.extend(['إجابة مختلفة'] * (3 - len(incorrect_choices)))

        all_choices = incorrect_choices[:3] + [question.correct_answer]
        random.shuffle(all_choices)

        return render_template(
            'quiz.html',
            question=question,
            options=all_choices,
            feedback=feedback,
            is_correct=is_correct,
        )

    @app.route('/admin', methods=['GET', 'POST'])
    def admin():
        if request.method == 'POST':
            question_text = request.form.get('question_text')
            correct_answer = request.form.get('correct_answer')
            wrong_answers = request.form.get('wrong_answers', '')

            wrong_answers_list = [ans.strip() for ans in wrong_answers.split('\n') if ans.strip()]

            if len(wrong_answers_list) < 3:
                flash('يجب إضافة ثلاث إجابات خاطئة على الأقل.', 'error')
                return redirect(url_for('admin'))

            if not question_text or not correct_answer:
                flash('يجب إدخال نص السؤال والإجابة الصحيحة.', 'error')
                return redirect(url_for('admin'))

            question = Question(text=question_text, correct_answer=correct_answer)
            db.session.add(question)
            db.session.flush()

            correct_option = AnswerOption(question_id=question.id, text=correct_answer, is_correct=True)
            db.session.add(correct_option)

            for answer in wrong_answers_list:
                db.session.add(AnswerOption(question_id=question.id, text=answer, is_correct=False))

            db.session.commit()
            flash('تمت إضافة السؤال بنجاح.', 'success')
            return redirect(url_for('admin'))

        questions = Question.query.options(joinedload(Question.options)).all()
        return render_template('admin.html', questions=questions)

    @app.route('/admin/edit/<int:question_id>', methods=['GET', 'POST'])
    def edit_question(question_id):
        question = Question.query.options(joinedload(Question.options)).get_or_404(question_id)

        if request.method == 'POST':
            question_text = request.form.get('question_text')
            correct_answer = request.form.get('correct_answer')
            wrong_answers = request.form.getlist('wrong_answers')
            wrong_answers_list = [answer.strip() for answer in wrong_answers if answer.strip()]

            if not question_text or not correct_answer:
                flash('يجب إدخال نص السؤال والإجابة الصحيحة.', 'error')
                return redirect(url_for('edit_question', question_id=question.id))

            if len(wrong_answers_list) < 3:
                flash('يجب الاحتفاظ بثلاث إجابات خاطئة على الأقل.', 'error')
                return redirect(url_for('edit_question', question_id=question.id))

            question.text = question_text
            question.correct_answer = correct_answer

            AnswerOption.query.filter_by(question_id=question.id).delete()
            db.session.add(AnswerOption(question_id=question.id, text=correct_answer, is_correct=True))

            for answer_text in wrong_answers_list:
                db.session.add(AnswerOption(question_id=question.id, text=answer_text, is_correct=False))

            db.session.commit()
            flash('تم تحديث السؤال بنجاح.', 'success')
            return redirect(url_for('admin'))

        incorrect_options = [option.text for option in question.options if not option.is_correct]
        return render_template('edit_question.html', question=question, incorrect_options=incorrect_options)


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
