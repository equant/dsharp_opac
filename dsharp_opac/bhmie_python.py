import numpy as np
import warnings
try:
    from numba import njit
    bhmie_type = 'numba'
except ImportError:
    warnings.warn('numba not available, opacity calculation will be very slow')

    def njit(ob):
        return ob

    bhmie_type = 'python'


@njit
def bhmie_python(x, refrel, theta):
    """
    The famous Bohren and Huffman Mie scattering code.
    This version was ported to Python from the f77 code from Bruce
    Draine, which can be downloaded from:
      https://www.astro.princeton.edu/~draine/scattering.html
    The code originates from the book by Bohren & Huffman (1983) on
    "Absorption and Scattering of Light by Small Particles".
    This python version was created by Cornelis Dullemond,
    February 2017.

    Arguments:
      x      = 2*pi*radius_grain/lambda
      refrel = Complex index of refraction (example: 1.5 + 0.01*1j)
      theta  = A numpy array of scattering angles between 0 and 180.

    Returns:
      S1     = A numpy array of complex phase function S1 (E perp to scattering plane)
               as a function of theta
      S2     = A numpy array of complex phase function S2 (E para to scattering plane)
               as a function of theta
      Qext   = C_ext/pi*a**2 = efficiency factor for extinction
      Qabs   = C_abs/pi*a**2 = efficiency factor for absoprtion
      Qsca   = C_sca/pi*a**2 = efficiency factor for scattering
      Qback  = (dC_sca/domega)/pi*a**2 = backscattering efficiency
               [NB: this is (1/4*pi) smaller than the "radar
                 backscattering efficiency"; see Bohren &
                 Huffman 1983 pp. 120-123]
      gsca   = <cos(theta)> for scattering
    """
    #
    # First check that the theta array goes from 0 to 180 or
    # 180 to 0, and store which is 0 and which is 180
    #
    nang = len(theta)
    if theta[0] == 0.0:
        if theta[nang - 1] != 180:
            raise AssertionError("Error in bhmie(): Angle grid must extend from 0 to 180 degrees.")
        iang0   = 0
        iang180 = nang - 1
    else:
        if theta[0] != 180:
            raise AssertionError("Error in bhmie(): Angle grid must extend from 0 to 180 degrees.")
        if theta[nang - 1] != 0:
            raise AssertionError("Error in bhmie(): Angle grid must extend from 0 to 180 degrees.")
        iang0   = nang - 1
        iang180 = 0
    #
    # Allocate the complex phase functions with double precision
    #
    S1     = np.zeros(nang, dtype=np.complex128)
    S2     = np.zeros(nang, dtype=np.complex128)
    #
    # Allocate and initialize arrays for the series expansion iteration
    #
    pi     = np.zeros(nang, dtype=np.float64)
    pi0    = np.zeros(nang, dtype=np.float64)
    pi1    = np.zeros(nang, dtype=np.float64) + 1.0
    tau    = np.zeros(nang, dtype=np.float64)
    #
    # Compute a alternative to x
    #
    y      = x * refrel
    #
    # Determine at which n=nstop to terminate the series expansion
    #
    xstop  = x + 4 * x**0.3333 + 2.0
    nstop  = int(np.floor(xstop))
    #
    # Determine the start of the logarithmic derivatives iteration
    #
    nmx    = int(np.floor(max(xstop, abs(y))) + 15)
    #
    # Compute the mu = cos(theta*pi/180.) for all scattering angles
    #
    mu     = np.cos(theta * np.pi / 180.)
    #
    # Now calculate the logarithmic derivative dlog by downward recurrence
    # beginning with initial value 0.+0j at nmx-1
    #
    dlog   = np.zeros(nmx, dtype=np.complex128)
    for n in range(nmx - 1):
        en            = float(nmx - n)
        dlog[nmx - n - 2] = en / y - 1.0 / (dlog[nmx - n - 1] + en / y)
    #
    # In preparation for the series expansion, reset some variables
    #
    psi0 = np.cos(x)
    psi1 = np.sin(x)
    chi0 = -np.sin(x)
    chi1 = np.cos(x)
    xi1  = psi1 - chi1 * 1j
    p    = -1.0
    Qsca = 0.0
    gsca = 0.0
    an   = 0j
    bn   = 0j
    #
    # Riccati-Bessel functions with real argument x
    # calculated by upward recurrence. This is where the
    # series expansion is done
    #
    for n in range(nstop):
        #
        # Basic calculation of the iteration
        #
        en      = float(n + 1)
        fn      = (2 * en + 1.0) / (en * (en + 1.0))
        psi     = (2 * en - 1.0) * psi1 / x - psi0
        chi     = (2 * en - 1.0) * chi1 / x - chi0
        xi      = psi - chi * 1j
        an1     = an
        bn1     = bn
        dum     = dlog[n] / refrel + en / x
        an      = (dum * psi - psi1) / (dum * xi - xi1)
        dum     = dlog[n] * refrel + en / x
        bn      = (dum * psi - psi1) / (dum * xi - xi1)
        #
        # Add contributions to Qsca and gsca
        #
        Qsca   += (2 * en + 1.0) * (abs(an)**2 + abs(bn)**2)
        dum     = (2 * en + 1.0) / (en * (en + 1.0))
        gsca   += dum * (an.real * bn.real + an.imag * bn.imag)
        dum     = (en - 1.0) * (en + 1.0) / en
        gsca   += dum * (an1.real * an.real + an1.imag * an.imag +
                         bn1.real * bn.real + bn1.imag * bn.imag)
        #
        # Now contribute to scattering intensity pattern as a function of angle
        #
        pi[:]   = pi1[:]
        tau[:]  = en * np.abs(mu[:]) * pi[:] - (en + 1.0) * pi0[:]
        #
        # For mu>=0
        #
        idx      = mu >= 0
        S1[idx] += fn * (an * pi[idx]  + bn * tau[idx])
        S2[idx] += fn * (an * tau[idx] + bn * pi[idx])
        #
        # For mu<0
        #
        p        = -p
        idx      = mu < 0
        S1[idx] += fn * p * (an * pi[idx] - bn * tau[idx])
        S2[idx] += fn * p * (bn * pi[idx] - an * tau[idx])
        #
        # Now prepare for the next iteration
        #
        psi0    = psi1
        psi1    = psi
        chi0    = chi1
        chi1    = chi
        xi1     = psi1 - chi1 * 1j
        pi1[:]  = ((2 * en + 1.0) * np.abs(mu[:]) * pi[:] - (en + 1.0) * pi0[:]) / en
        pi0[:]  = pi[:]
    #
    # Now do the final calculations
    #
    gsca  = 2 * gsca / Qsca
    Qsca  = (2.0 / (x * x)) * Qsca
    Qext  = (4.0 / (x * x)) * S1[iang0].real
    Qback = (abs(S1[iang180]) / x)**2 / np.pi
    Qabs  = Qext - Qsca
    #
    # Return results
    #
    return S1, S2, Qext, Qabs, Qsca, Qback, gsca.real


def bhmie_python_wrapper(x, nk, nangles):
    """
    wrapper for the python version to be callable just like the fortran version.

    Arguments:
    ----------

    x : float
        size parameter 2 pi a / lambda

    nk : complex
        complex ref. index = n + i * k, e.g. `complex(1.,0.)`

    nangles : int
        number of angles between 0 and 90 degree. Will return S1 & S2 at
        2 * nangles - 1 angles between 0 and 180 degree.

    Output:
    -------
    S1, S2, Qext, Qabs, Qsca, Qback, gsca

    S1, S2 : arrays
        the matrix elements as function of angle

    Qext, Qabs, Qsca, Qback : float
        the extinction, absorption, scattering, backscattering coefficients

    gsca : float
        Henyey-Greenstein asymmetry factor
    """
    theta = np.linspace(0., 180., 2 * nangles - 1)
    return bhmie_python(x, nk, theta)
