# Arquivo: core/custom_widgets.py
import ast
import operator
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtGui import QValidator
from PySide6.QtCore import Qt

class MathDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Operadores permitidos para o cálculo seguro
        self.allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos
        }

    def textFromValue(self, value):
        # Substitui o ponto por vírgula para a exibição no padrão PT-BR se necessário, 
        # ou mantém o padrão dependendo do locale do sistema.
        return super().textFromValue(value)

    def valueFromText(self, text):
        # Remove espaços e substitui vírgulas por pontos para o cálculo
        clean_text = text.replace(" ", "").replace(",", ".")
        
        # Remove o sufixo (ex: " mm" ou " px") antes de calcular
        if self.suffix() and clean_text.endswith(self.suffix().strip()):
            clean_text = clean_text[:-len(self.suffix().strip())]
            
        try:
            # Tenta avaliar a expressão matemática de forma segura
            result = self._evaluate_math(clean_text)
            return float(result)
        except Exception:
            # Tenta avaliar removendo operadores ou pontos flutuantes do final
            try:
                transient_clean = clean_text.rstrip('.,+-*/')
                if transient_clean:
                    return float(self._evaluate_math(transient_clean))
            except:
                pass
            return self.value()

    def validate(self, input_text, pos):
        # Permitimos qualquer caractere temporariamente durante a digitação 
        # para que o usuário possa digitar operadores como +, -, *, /
        return QValidator.State.Acceptable, input_text, pos

    def _evaluate_math(self, expr_str):
        """Avalia uma expressão matemática simples de forma segura usando AST."""
        try:
            node = ast.parse(expr_str, mode='eval')
            return self._eval_node(node.body)
        except Exception:
            raise ValueError(f"Expressão inválida: {expr_str}")

    def _eval_node(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Apenas números são permitidos")
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_type = type(node.op)
            if op_type in self.allowed_operators:
                return self.allowed_operators[op_type](left, right)
            raise ValueError(f"Operador não suportado: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            if op_type in self.allowed_operators:
                return self.allowed_operators[op_type](operand)
            raise ValueError(f"Operador unário não suportado: {op_type}")
        else:
            raise ValueError(f"Tipo de nó não suportado: {type(node)}")