from netgen.csg import *
import netgen.meshing as netgen

from ngsolve import *
from ngsolve.ngstd import MPIManager
from ngsolve.la import DISTRIBUTED
from ngsolve.la import CUMULATED

rank = MPIManager.GetRank()
np = MPIManager.GetNP()


def MakeGeometry():
    geometry = CSGeometry()
    box = OrthoBrick(Pnt(-1,-1,-1),Pnt(2,1,2)).bc("outer")

    core = OrthoBrick(Pnt(0,-0.05,0),Pnt(0.8,0.05,1))- \
           OrthoBrick(Pnt(0.1,-1,0.1),Pnt(0.7,1,0.9))- \
           OrthoBrick(Pnt(0.5,-1,0.4),Pnt(1,1,0.6)).maxh(0.2).mat("core")
    
    coil = (Cylinder(Pnt(0.05,0,0), Pnt(0.05,0,1), 0.3) - \
            Cylinder(Pnt(0.05,0,0), Pnt(0.05,0,1), 0.15)) * \
            OrthoBrick (Pnt(-1,-1,0.3),Pnt(1,1,0.7)).maxh(0.2).mat("coil")
    
    geometry.Add ((box-core-coil).mat("air"))
    geometry.Add (core)
    geometry.Add (coil)
    return geometry

if rank==0:
    ngmesh = MakeGeometry().GenerateMesh(maxh=0.5)
    ngmesh.Save("some_mesh.vol")

MPIManager.Barrier()

ngmesh = netgen.Mesh(dim=3)
ngmesh.Load("some_mesh.vol")
mesh = Mesh(ngmesh)

mesh.Curve(5)

ngsglobals.msg_level = 5

fes = HCurl(mesh, order=4, dirichlet="outer", flags = { "nograds" : True })

u = fes.TrialFunction()
v = fes.TestFunction()

mur = { "core" : 1000, "coil" : 1, "air" : 1 }
mu0 = 1.257e-6

nu_coef = [ 1/(mu0*mur[mat]) for mat in mesh.GetMaterials() ]

nu = CoefficientFunction(nu_coef)
a = BilinearForm(fes, symmetric=True)
a += SymbolicBFI(nu*curl(u)*curl(v) + 1e-6*nu*u*v)

#c = Preconditioner(a, type="bddc", flags={"inverse":"masterinverse"})
c = Preconditioner(a, type="bddc", flags={"inverse":"mumps"})

f = LinearForm(fes)
f += SymbolicLFI(CoefficientFunction((y,0.05-x,0)) * v, definedon=mesh.Materials("coil"))

u = GridFunction(fes)


a.Assemble()
f.Assemble()
solver = CGSolver(mat=a.mat, pre=c.mat)
u.vec.data = solver * f.vec


import os
output_path = os.path.dirname(os.path.realpath(__file__)) + "/cmagnet_output"
if rank==0 and not os.path.exists(output_path):
    os.mkdir(output_path)
MPIManager.Barrier() #wait until master has created the directory!!
vtk = VTKOutput(ma=mesh, coefs=[u.Deriv()], names=["sol"], filename=output_path+"/vtkout_p"+str(rank), subdivision=2)
vtk.Do()

#Draw (u.Deriv(), mesh, "B-field", draw_surf=False)
