from pytest import approx
import numpy as np

from ipp import Csy

def test_csy_conversions():
  # euler angles with gimbal lock
  csy = Csy(653.0, 134.0, 126.5, 0, -90, 0)

  # needs a couple conversions to stabilize
  mat = csy.toMatrix4()
  newcsy = Csy.fromMatrix4(mat)
  mat2 = newcsy.toMatrix4()
  newcsy2 = Csy.fromMatrix4(mat)

  assert newcsy.x == approx(newcsy2.x)
  assert newcsy.y == approx(newcsy2.y)
  assert newcsy.z == approx(newcsy2.z)
  assert newcsy.theta == approx(newcsy2.theta)
  assert newcsy.psi == approx(newcsy2.psi)
  assert newcsy.phi == approx(newcsy2.phi)

def test_csy_conversions2():
  csy = Csy(653.0, 134.0, 126.5, 34, 34, 155)

  mat = csy.toMatrix4()
  newcsy = Csy.fromMatrix4(mat)

  assert newcsy.x == approx(csy.x)
  assert newcsy.y == approx(csy.y)
  assert newcsy.z == approx(csy.z)
  assert newcsy.theta == approx(csy.theta)
  assert newcsy.psi == approx(csy.psi)
  assert newcsy.phi == approx(csy.phi)

def test_csy_conversions3():
  csy = Csy(653.0, 134.0, 126.5, 0, -90, 0)

  mat = csy.toMatrix4()

  assert mat == approx(np.array([ [  0, 1, 0, 653 ],
                                  [ -1, 0, 0, 134 ],
                                  [  0, 0, 1, 126.5 ],
                                  [  0, 0, 0, 1 ]]))
